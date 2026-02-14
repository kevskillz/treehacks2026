"""
Backend: Twilio SMS feedback (Claude) + project/plan/coder workflow (Claude code, create PR).
- No tweet tracking. All project data comes from DB.
- Twilio handler saves feedback to DB (user_feedback) once Claude has determined it from each user.
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from dotenv import load_dotenv
import os
import logging
import uuid
from uuid import UUID

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from supabase import create_client, Client
from models import (
    UpdateProjectStatusRequest,
    CreateExecutionLogRequest,
    CreateRepoConfigRequest,
    ExecuteCoderRequest,
    ProjectStatus,
    LogLevel,
)
import db
from twilio.twiml.messaging_response import MessagingResponse
from claude import (
    get_feedback_reply,
    generate_plan,
    enrich_issue_with_context,
    verify_issue_formatting,
)
from coder import ClaudeCoderOrchestrator

app = Flask(__name__)
CORS(app)

supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
)
coder_orchestrator = ClaudeCoderOrchestrator(supabase)

# SMS: per-phone conversation history
conversations = {}


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "vector-backend"}), 200


@app.route("/", methods=["GET"])
def root():
    return jsonify({"service": "SMS Feedback + Coder API", "docs": "see README"}), 200


# ---------- Twilio SMS (Claude feedback) ----------
@app.route("/sms/incoming", methods=["POST"])
def twilio_webhook():
    """Twilio webhook: reply with TwiML using Claude; when feedback is determined, save to DB."""
    import json as _json
    body = (request.form.get("Body") or "").strip()
    phone = (request.form.get("From") or "").strip() or "unknown"
    if not body:
        twiml = '<?xml version="1.0" encoding="UTF-8"?><Response><Message>Send any message to share feedback—we\'ll ask until clear. Thanks!</Message></Response>'
        return Response(twiml, mimetype="application/xml")
    try:
        history = conversations.setdefault(phone, [])
        reply_text, summary = get_feedback_reply(body, history)
        history.append({"role": "user", "content": body})
        history.append({"role": "assistant", "content": reply_text})
        if summary:
            db.create_feedback(supabase, phone, summary, raw_messages=_json.dumps(history))
            conversations.pop(phone, None)
    except Exception as e:
        logger.exception("Claude feedback failed")
        reply_text = "Something went wrong. Try again in a moment."
    resp = MessagingResponse()
    resp.message(reply_text)
    return Response(str(resp), mimetype="application/xml")


# ---------- Projects ----------
@app.route("/api/projects/<project_id>", methods=["GET"])
def get_project(project_id):
    try:
        data = db.get_project_with_plan(supabase, project_id)
        if not data:
            return jsonify({"error": "Project not found"}), 404
        logs = db.get_execution_logs(supabase, project_id)
        return jsonify({
            "project": data["project"].model_dump(mode="json"),
            "plan": data["plan"].model_dump(mode="json") if data["plan"] else None,
            "logs": [log.model_dump(mode="json") for log in logs],
        }), 200
    except Exception as e:
        logger.error("Error getting project: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/projects/<project_id>/generate-plan", methods=["POST"])
def generate_plan_route(project_id):
    try:
        db.update_project_status(supabase, project_id, ProjectStatus.PLANNING)
        db.create_execution_log(supabase, project_id, "Plan generation started", LogLevel.INFO, "generate_plan")
        plan = generate_implementation_plan(project_id)
        if plan:
            return jsonify({"status": "success", "message": "Plan generated", "plan_id": str(plan.id)}), 200
        return jsonify({"status": "error", "message": "Failed to generate plan"}), 500
    except Exception as e:
        logger.error("Error generating plan: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/projects/<project_id>/status", methods=["PUT"])
def update_project_status_endpoint(project_id):
    try:
        data = UpdateProjectStatusRequest(**request.json)
        project = db.update_project_status(supabase, project_id, data.status, data.metadata)
        db.create_execution_log(supabase, project_id, f"Status: {data.status.value}", LogLevel.INFO, "status_update", data.metadata)
        return jsonify({"status": "updated", "project": project.model_dump(mode="json")}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/projects/<project_id>/logs", methods=["POST"])
def add_execution_log(project_id):
    try:
        data = CreateExecutionLogRequest(**request.json)
        log = db.create_execution_log(supabase, project_id, data.message, data.log_level, data.step_name, data.metadata)
        return jsonify({"status": "logged", "log": log.model_dump(mode="json")}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/projects/<project_id>/logs", methods=["GET"])
def get_execution_logs_endpoint(project_id):
    try:
        logs = db.get_execution_logs(supabase, project_id)
        return jsonify({"logs": [log.model_dump(mode="json") for log in logs]}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- Plans ----------
@app.route("/api/plans/<plan_id>", methods=["GET"])
def get_plan_route(plan_id):
    try:
        data = db.get_plan_with_project(supabase, plan_id)
        if not data:
            return jsonify({"error": "Plan not found"}), 404
        return jsonify({
            "plan": data["plan"].model_dump(mode="json"),
            "project": data["project"].model_dump(mode="json") if data["project"] else None,
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/plans/<plan_id>/approve", methods=["POST"])
def approve_plan_route(plan_id):
    try:
        user_id = request.json.get("user_id") if request.json else None
        content = request.json.get("content") if request.json else None
        plan = db.approve_plan(supabase, plan_id, user_id, content)
        db.update_project_status(supabase, plan.project_id, ProjectStatus.EXECUTING)
        db.create_execution_log(supabase, plan.project_id, "Plan approved, starting Claude code execution", LogLevel.INFO, "plan_approval")
        project = db.get_project(supabase, plan.project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 500
        try:
            result = coder_orchestrator.execute_issue_workflow(plan.project_id, project.repo_config_id)
            return jsonify({
                "status": "approved",
                "plan": plan.model_dump(mode="json"),
                "execution": {"status": "completed", "result": result},
            }), 200
        except Exception as workflow_error:
            logger.exception("Workflow failed: %s", workflow_error)
            return jsonify({
                "status": "approved",
                "plan": plan.model_dump(mode="json"),
                "execution": {"status": "failed", "error": str(workflow_error)},
            }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- Repos ----------
@app.route("/api/repos", methods=["POST"])
def create_repo_config_endpoint():
    try:
        data = CreateRepoConfigRequest(**request.json)
        repo_config = db.create_repo_config(supabase, data.model_dump())
        return jsonify({"status": "created", "repo_config": repo_config.model_dump(mode="json")}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/repos/<repo_config_id>/projects", methods=["GET"])
def get_repo_projects(repo_config_id):
    try:
        projects = db.get_projects_by_repo(supabase, repo_config_id)
        return jsonify({"projects": [p.model_dump(mode="json") for p in projects]}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/repos/<repo_config_id>/active-project", methods=["GET"])
def get_active_project_endpoint(repo_config_id):
    try:
        project = db.get_or_create_active_project(supabase, repo_config_id)
        return jsonify({"project_id": str(project.id), "project": project.model_dump(mode="json")}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- Feedback (from DB; collected via Twilio) ----------
@app.route("/api/feedback", methods=["GET"])
def list_feedback_endpoint():
    """List recent user feedback (stored when Twilio/Claude determined it)."""
    try:
        limit = request.args.get("limit", 100, type=int)
        feedback = db.list_feedback(supabase, limit=min(limit, 500))
        return jsonify({"feedback": [f.model_dump(mode="json") for f in feedback]}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/feedback/by-phone/<path:phone>", methods=["GET"])
def get_feedback_by_phone_endpoint(phone):
    try:
        feedback = db.get_feedback_by_phone(supabase, phone)
        return jsonify({"feedback": [f.model_dump(mode="json") for f in feedback]}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- Coder ----------
@app.route("/api/coder/execute", methods=["POST"])
def execute_coder_workflow():
    try:
        data = ExecuteCoderRequest(**request.json)
        project = db.get_project(supabase, data.project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404
        if project.status != ProjectStatus.EXECUTING:
            return jsonify({"error": "Project must be in executing status. Approve plan first."}), 400
        if not project.github_issue_url:
            return jsonify({"error": "Project missing GitHub issue. Call project approve first."}), 400
        repo_config = db.get_repo_config(supabase, project.repo_config_id)
        if not repo_config:
            return jsonify({"error": "Repo config not found"}), 404
        execution_id = str(uuid.uuid4())
        try:
            result = coder_orchestrator.execute_issue_workflow(data.project_id, project.repo_config_id)
            return jsonify({
                "status": "completed",
                "execution_id": execution_id,
                "project_id": str(data.project_id),
                "github_issue_url": project.github_issue_url,
                "result": result,
            }), 200
        except Exception as workflow_error:
            logger.exception("Workflow failed: %s", workflow_error)
            return jsonify({
                "status": "failed",
                "execution_id": execution_id,
                "project_id": str(data.project_id),
                "error": str(workflow_error),
            }), 500
    except Exception as e:
        logger.exception("Coder execute: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/coder/status/<project_id>", methods=["GET"])
def get_coder_status(project_id):
    try:
        project = db.get_project(supabase, project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404
        logs = db.get_execution_logs(supabase, project_id)
        session = db.get_coder_session_by_project(supabase, project_id)
        progress_map = {"pending": 0.0, "planning": 0.2, "provisioning": 0.3, "executing": 0.6, "completed": 1.0, "failed": 0.0}
        progress = progress_map.get(project.status.value, 0.0)
        current_step = logs[0].step_name if logs else None
        return jsonify({
            "status": project.status.value,
            "current_step": current_step,
            "progress": progress,
            "logs": [log.model_dump(mode="json") for log in logs[:20]],
            "session": session.model_dump(mode="json") if session else None,
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- Helpers ----------
def generate_implementation_plan(project_id: str, repo_context: dict = None):
    """Generate plan from project title/description in DB (no tweet data)."""
    data = db.get_project_with_plan(supabase, project_id)
    if not data:
        raise ValueError(f"Project {project_id} not found")
    project, plan_existing = data["project"], data.get("plan")
    repo = db.get_repo_config(supabase, project.repo_config_id)
    if not repo:
        raise ValueError("Repo config not found")
    sandbox_ctx = None
    feedback_texts = [project.title]
    if project.description:
        feedback_texts.append(project.description)
    if not feedback_texts or (len(feedback_texts) == 1 and not feedback_texts[0].strip()):
        raise ValueError("Project has no title/description to generate plan from")
    try:
        if not repo_context:
            from sandbox import create_sandbox, cleanup_sandbox
            sandbox_ctx = create_sandbox(project_id, repo)
            from testing import detect_repo_context
            rc = detect_repo_context(sandbox_ctx.repo_path)
            repo_context = {
                "primary_language": rc.primary_language,
                "test_framework": rc.test_framework,
                "build_system": rc.build_system,
                "structure_summary": rc.structure_summary,
            }
            from sandbox import save_repo_context
            save_repo_context(UUID(project_id), repo_context)
        plan_content = generate_plan(
            feedback_texts, repo.github_owner, repo.github_repo, repo.github_branch, repo_context
        )
        plan = db.create_plan(supabase, {
            "title": project.title,
            "content": plan_content,
            "project_id": str(project_id),
            "version": 1,
        })
        supabase.table("projects").update({
            "plan_id": str(plan.id),
            "status": ProjectStatus.PROVISIONING.value,
        }).eq("id", str(project_id)).execute()
        db.create_execution_log(supabase, project_id, "Plan generated", LogLevel.INFO, "plan_complete")
        return plan
    except Exception as e:
        db.update_project_status(supabase, project_id, ProjectStatus.FAILED)
        raise
    finally:
        if sandbox_ctx:
            try:
                from sandbox import cleanup_sandbox
                cleanup_sandbox(project_id)
            except Exception:
                pass


@app.route("/api/projects/<project_id>/approve", methods=["POST"])
def approve_project_request(project_id):
    try:
        request_data = request.json if request.json else {}
        auto_generate_plan = request_data.get("auto_generate_plan", True)
        project = db.get_project(supabase, project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404
        if project.status != ProjectStatus.PENDING:
            return jsonify({"error": f"Project must be pending (current: {project.status.value})"}), 400
        repo_config = db.get_repo_config(supabase, project.repo_config_id)
        if not repo_config:
            return jsonify({"error": "Repo config not found"}), 404
        from github_client import create_issue
        from sandbox import create_sandbox, save_repo_context
        from testing import detect_repo_context
        db.create_execution_log(supabase, project_id, "Detecting code context", LogLevel.INFO, "detect_context")
        sandbox_ctx = create_sandbox(project_id, repo_config)
        repo_context_obj = detect_repo_context(sandbox_ctx.repo_path)
        repo_context = {
            "primary_language": repo_context_obj.primary_language,
            "test_framework": repo_context_obj.test_framework,
            "build_system": repo_context_obj.build_system,
            "structure_summary": repo_context_obj.structure_summary,
        }
        save_repo_context(UUID(project_id), repo_context)
        db.create_execution_log(supabase, project_id, "Enriching issue", LogLevel.INFO, "enrich_issue")
        enriched = enrich_issue_with_context(project.title, project.description or "", repo_context)
        verified = verify_issue_formatting(enriched["title"], enriched["description"])
        enriched_title, enriched_description = verified["title"], verified["description"]
        db.create_execution_log(supabase, project_id, "Creating GitHub issue", LogLevel.INFO, "create_issue")
        labels = [project.ticket_type]
        if project.severity_score > 100:
            labels.append("high-priority")
        issue = create_issue(enriched_title, enriched_description, labels, repo_config)
        issue_url = f"https://github.com/{repo_config.github_owner}/{repo_config.github_repo}/issues/{issue.number}"
        db.update_project_status(supabase, project_id, ProjectStatus.PLANNING, {
            "github_issue_number": issue.number,
            "github_issue_url": issue_url,
        })
        db.create_execution_log(supabase, project_id, f"Issue #{issue.number} created", LogLevel.INFO, "issue_created")
        plan_id = None
        if auto_generate_plan:
            try:
                plan = generate_implementation_plan(project_id, repo_context=repo_context)
                plan_id = str(plan.id) if plan else None
            except Exception as plan_error:
                logger.error("Plan generation failed: %s", plan_error)
                db.create_execution_log(supabase, project_id, f"Plan failed: {plan_error}", LogLevel.WARNING, "plan_generation_failed")
        return jsonify({
            "status": "approved",
            "github_issue_url": issue_url,
            "github_issue_number": issue.number,
            "plan_id": plan_id,
            "message": "Project approved, issue created",
        }), 200
    except Exception as e:
        logger.exception("Approve failed: %s", e)
        db.create_execution_log(supabase, project_id, f"Approval failed: {e}", LogLevel.ERROR, "approval_error")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="127.0.0.1", port=port, debug=True)
