# Next.js 15.3 + Supabase + TypeScript Best Practices

## Package Manager

**This project uses pnpm.** Always use `pnpm` instead of `npm` or `yarn`.

```bash
# Install dependencies
pnpm install

# Add a package
pnpm add <package>

# Add a dev dependency
pnpm add -D <package>

# Run scripts
pnpm dev
pnpm build
pnpm test
```

## Core Principles

### 1. Type Generation is Non-Negotiable

```bash
# After ANY schema change:
supabase gen types --local > types/supabase.ts

# Automate with git hooks:
# .husky/pre-commit
if git diff --cached --name-only | grep -q "supabase/migrations"; then
  pnpm run types:generate
  git add types/supabase.ts
fi
```

### 2. Server-First Architecture (Next.js 15.3)

```typescript
// Server Components by default
export default async function Page() {
  const data = await getServerData() // Direct DB calls
  return <ClientComponent initialData={data} />
}

// Use after() for non-blocking operations
import { after } from 'next/server'

export async function createPost(data: PostInput) {
  const post = await db.posts.create(data)

  after(async () => {
    // Non-blocking: analytics, cache warming, webhooks
    await trackEvent('post_created', { postId: post.id })
    await sendNotification(post.authorId)
  })

  return post
}
```

### 3. Supabase Client Separation

```typescript
// lib/supabase/client.ts - Browser only
import { createBrowserClient } from '@supabase/ssr'
import type { Database } from '@/types/supabase'

export const createClient = () =>
  createBrowserClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )

// lib/supabase/server.ts - Server only
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

export const createClient = async () => {
  const cookieStore = await cookies()
  return createServerClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => cookieStore.getAll(),
        setAll: (cookiesToSet) => {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          )
        },
      },
    }
  )
}
```

### Supabase Migration-First Development

When working with Supabase databases, **ALWAYS** use migrations for ANY schema changes:

### Core Rules

1. **NEVER modify the database directly** - No manual CREATE TABLE, ALTER TABLE, etc.

2. **ALWAYS create a migration file** for schema changes:
    ```bash
    supabase migration new descriptive_name_here
    ```

3. **Migration naming convention**:
    - `create_[table]_table` - New tables
    - `add_[column]_to_[table]` - New columns
    - `update_[table]_[change]` - Modifications
    - `create_[name]_index` - Indexes
    - `add_[table]_rls` - RLS policies

4. **After EVERY migration**:
    ```bash
    supabase db reset                          # Apply locally
    supabase gen types --local > types/supabase.ts  # Update types
    ```

5. **Example workflow for adding a field**:
    ```bash
    # Wrong
    ALTER TABLE posts ADD COLUMN views INTEGER DEFAULT 0;

    # Right
    supabase migration new add_views_to_posts
    # Then write SQL in the generated file
    # Then: supabase db reset && pnpm run db:types
    ```

6. **Include in EVERY migration**:
    - Enable RLS on new tables
    - Add proper indexes
    - Consider adding triggers for updated_at

7. **Commit both**:
    - Migration file (`supabase/migrations/*.sql`)
    - Updated types (`types/supabase.ts`)

This ensures reproducible database states across all environments and team members.

## Project Structure (Next.js 15.3 + Supabase)

```
├── app/                      # App Router
│   ├── (auth)/              # Auth group routes
│   ├── (dashboard)/         # Protected routes
│   ├── api/                 # API routes
│   └── globals.css          # Tailwind v4
├── components/
│   ├── ui/                  # shadcn/ui components
│   └── features/            # Feature components
├── lib/
│   ├── supabase/           # Client configs
│   └── utils.ts            # cn() + helpers
├── server/                  # Server-only code
│   ├── queries/            # DB queries
│   └── actions/            # Server Actions
├── hooks/                   # Client hooks
├── test/                    # Test utilities
│   └── setup.ts            # Vitest setup
├── types/
│   └── supabase.ts         # Generated types
└── supabase/
    ├── migrations/         # Database migrations
    └── config.toml         # Supabase configuration
```

## Next.js 15.3 Patterns

### Server Actions with Revalidation

```typescript
// server/actions/posts.ts
'use server'

import { revalidateTag, revalidatePath } from 'next/cache'
import { after } from 'next/server'

export async function createPost(formData: PostInput) {
  const supabase = await createClient()

  const { data, error } = await supabase
    .from('posts')
    .insert(formData)
    .select()
    .single()

  if (error) throw error

  // Immediate revalidation
  revalidateTag('posts')
  revalidatePath('/dashboard')

  // Deferred operations
  after(async () => {
    await notifySubscribers(data.id)
  })

  return data
}
```

### Form Component with Prefetching

```typescript
// Using Next.js 15.3 stable Form component
import Form from 'next/form'

export function SearchForm() {
  return (
    <Form action="/search" prefetch={true}>
      <input name="q" placeholder="Search..." />
      <button type="submit">Search</button>
    </Form>
  )
}
```

### Connection API for Performance

```typescript
// Warm connections early for better performance
import { connection } from 'next/server'

export default async function Layout({ children }) {
  // Pre-warm database connection
  await connection()

  // Pre-connect to external services
  await fetch('https://api.service.com/warmup', {
    method: 'HEAD'
  })

  return <>{children}</>
}
```

## Authentication Pattern (Already Implemented)

The starter includes a complete authentication setup:
- Sign up/Sign in pages at `/signup` and `/signin`
- Protected dashboard routes under `app/(dashboard)/`
- Server actions in `server/actions/auth.ts`
- Auth middleware configuration
- Profile creation on signup

```typescript
// middleware.ts
import { updateSession } from '@/lib/supabase/middleware'

export async function middleware(request: NextRequest) {
  return await updateSession(request)
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'],
}

// app/(dashboard)/layout.tsx
import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'

export default async function DashboardLayout({ children }) {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) redirect('/login')

  return <>{children}</>
}

// server/actions/auth.ts - Available auth actions
export async function signUp(formData: FormData)
export async function signIn(formData: FormData)
export async function signOut()
```

## UI Components (shadcn/ui + Tailwind v4)

### Tailwind v4 Configuration

```css
/* app/globals.css */
@import "tailwindcss";

/* Define design tokens in @theme */
@theme {
  --color-primary: oklch(24% 0.15 256);
  --color-background: oklch(100% 0 0);
  --color-foreground: oklch(10% 0 0);

  --font-sans: 'Inter', system-ui, sans-serif;
  --radius: 0.5rem;
}

/* No more @tailwind directives or @layer needed */
```

### Component Setup

```bash
# Initialize shadcn/ui with Tailwind v4
pnpm dlx shadcn@latest init

# Add components as needed
pnpm dlx shadcn@latest add button form card toast
```

```typescript
// Feature component using shadcn/ui
import { Button } from '@/components/ui/button'
import { useToast } from '@/hooks/use-toast'

export function PostCard({ post }: { post: Post }) {
  const { toast } = useToast()

  async function handleLike() {
    const result = await likePost(post.id)

    toast({
      title: result.success ? "Liked!" : "Error",
      variant: result.success ? "default" : "destructive",
    })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{post.title}</CardTitle>
      </CardHeader>
      <CardContent>{post.content}</CardContent>
      <CardFooter>
        <Button onClick={handleLike}>Like</Button>
      </CardFooter>
    </Card>
  )
}
```

## Real-time Subscriptions

```typescript
// hooks/use-realtime.ts
export function useRealtime<T extends keyof Database['public']['Tables']>(
  table: T,
  filter?: string
) {
  const [data, setData] = useState<Tables<T>[]>([])
  const supabase = createClient() // Client-side only

  useEffect(() => {
    const channel = supabase
      .channel(`realtime:${table}`)
      .on('postgres_changes',
        { event: '*', schema: 'public', table, filter },
        (payload) => {
          if (payload.eventType === 'INSERT') {
            setData(prev => [payload.new as Tables<T>, ...prev])
          }
          // Handle UPDATE, DELETE
        }
      )
      .subscribe()

    return () => { channel.unsubscribe() }
  }, [table, filter])

  return data
}
```

## Testing Infrastructure (Vitest)

### When to Test

- **Business logic** in utilities and hooks
- **Server Actions** with mocked Supabase client
- **Component behavior** not visual appearance
- **Error states** and edge cases

### Setup

```bash
pnpm add -D vitest @testing-library/react @testing-library/user-event @vitejs/plugin-react jsdom
```

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: './test/setup.ts',
    globals: true,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './'),
    },
  },
})

// test/setup.ts
import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Mock Supabase client
vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    from: vi.fn(() => ({
      select: vi.fn(() => ({
        eq: vi.fn(() => Promise.resolve({ data: [], error: null })),
      })),
      insert: vi.fn(() => ({
        select: vi.fn(() => ({
          single: vi.fn(() => Promise.resolve({ data: {}, error: null })),
        })),
      })),
    })),
    auth: {
      getUser: vi.fn(() => Promise.resolve({ data: { user: null }, error: null })),
    },
  }),
}))
```

### Testing Patterns

```typescript
// components/features/posts/__tests__/post-card.test.tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PostCard } from '../post-card'

describe('PostCard', () => {
  const mockPost = {
    id: '1',
    title: 'Test Post',
    content: 'Test content',
    author: { name: 'John' },
  }

  it('renders post content', () => {
    render(<PostCard post={mockPost} />)
    expect(screen.getByText('Test Post')).toBeInTheDocument()
    expect(screen.getByText('Test content')).toBeInTheDocument()
  })

  it('calls onLike when like button clicked', async () => {
    const onLike = vi.fn()
    const user = userEvent.setup()

    render(<PostCard post={mockPost} onLike={onLike} />)
    await user.click(screen.getByRole('button', { name: /like/i }))

    expect(onLike).toHaveBeenCalledWith(mockPost.id)
  })
})

// server/actions/__tests__/posts.test.ts
import { createPost } from '../posts'
import { createClient } from '@/lib/supabase/server'

vi.mock('@/lib/supabase/server')

describe('createPost', () => {
  it('creates post and returns data', async () => {
    const mockSupabase = {
      from: vi.fn(() => ({
        insert: vi.fn(() => ({
          select: vi.fn(() => ({
            single: vi.fn(() => ({
              data: { id: '1', title: 'New Post' },
              error: null
            })),
          })),
        })),
      })),
    }

    vi.mocked(createClient).mockResolvedValue(mockSupabase as any)

    const result = await createPost({ title: 'New Post', content: 'Content' })
    expect(result).toEqual({ id: '1', title: 'New Post' })
  })

  it('throws error on database failure', async () => {
    const mockSupabase = {
      from: vi.fn(() => ({
        insert: vi.fn(() => ({
          select: vi.fn(() => ({
            single: vi.fn(() => ({
              data: null,
              error: new Error('Database error')
            })),
          })),
        })),
      })),
    }

    vi.mocked(createClient).mockResolvedValue(mockSupabase as any)

    await expect(createPost({ title: 'Test', content: 'Test' }))
      .rejects.toThrow('Database error')
  })
})
```

## Database Patterns

### Type-Safe Queries

```typescript
// server/queries/posts.ts
import type { Database } from '@/types/supabase'

type Tables<T extends keyof Database['public']['Tables']> =
  Database['public']['Tables'][T]['Row']

export async function getPosts() {
  const supabase = await createClient()

  const { data, error } = await supabase
    .from('posts')
    .select(`
      *,
      profiles!inner(username, avatar_url)
    `)
    .order('created_at', { ascending: false })

  if (error) throw error
  return data
}
```

### Row Level Security

```sql
-- Always enable RLS
ALTER TABLE posts ENABLE ROW LEVEL SECURITY;

-- Public read, authenticated write
CREATE POLICY "Public posts are viewable by everyone" ON posts
  FOR SELECT USING (published = true);

CREATE POLICY "Users can insert their own posts" ON posts
  FOR INSERT WITH CHECK (auth.uid() = author_id);
```

## Performance Optimization

### Parallel Data Loading

```typescript
// Load data in parallel in Server Components
export default async function DashboardPage() {
  const [posts, profile, stats] = await Promise.all([
    getPosts(),
    getProfile(),
    getStats()
  ])

  return (
    <Dashboard
      posts={posts}
      profile={profile}
      stats={stats}
    />
  )
}
```

### Streaming with Suspense

```typescript
import { Suspense } from 'react'

export default function Page() {
  return (
    <>
      <Header />
      <Suspense fallback={<PostsSkeleton />}>
        <PostsList />
      </Suspense>
    </>
  )
}

async function PostsList() {
  const posts = await getPosts() // This can be slow
  return <>{posts.map(post => <PostCard key={post.id} post={post} />)}</>
}
```

## Development Workflow

### Essential Scripts

```json
{
  "scripts": {
    "dev": "next dev --turbo",
    "build": "next build",
    "test": "vitest",
    "test:ui": "vitest --ui",
    "test:coverage": "vitest --coverage",
    "db:types": "supabase gen types --local > types/supabase.ts",
    "db:push": "supabase db push",
    "db:reset": "supabase db reset"
  }
}
```

### Environment Variables

```typescript
// lib/env.ts - Validated env vars
import { z } from 'zod'

const envSchema = z.object({
  NEXT_PUBLIC_SUPABASE_URL: z.string().url(),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string(),
  SUPABASE_SERVICE_ROLE_KEY: z.string().optional(),
})

export const env = envSchema.parse(process.env)
```

## Key Commands

```bash
# Development
pnpm dev                    # Fast refresh with Turbopack
supabase start              # Local Supabase

# Testing
pnpm test                   # Run tests in watch mode
pnpm test:ui                # Open Vitest UI
pnpm test:coverage          # Generate coverage report

# Database
supabase db reset           # Reset + migrate
supabase gen types --local > types/supabase.ts

# UI Components
pnpm dlx shadcn@latest add  # Add components

# Production
pnpm build                  # Type-safe build
supabase db push            # Deploy migrations
```

## Critical Rules

1. **Always use pnpm** - never npm or yarn
2. **Always regenerate types after schema changes**
3. **Use Server Components by default, Client Components when needed**
4. **Separate server and client Supabase instances**
5. **Use `after()` for non-blocking operations**
6. **Enable RLS on all tables**
7. **Compose UI with shadcn/ui components**
8. **Validate environment variables with Zod**
9. **Use Server Actions for mutations**
10. **Implement proper error boundaries**
11. **Stream data with Suspense for better UX**
12. **Test business logic, not implementation details**

## Code Style and Structure

### TypeScript Best Practices
- Write concise, technical TypeScript code with accurate examples
- Use functional and declarative programming patterns; avoid classes
- Favor iteration and modularization over code duplication
- Use descriptive variable names with auxiliary verbs (e.g., `isLoading`, `hasError`)
- Structure files with exported components, subcomponents, helpers, static content, and types

### Naming Conventions
- Use lowercase with dashes for directory names (e.g., `components/auth-wizard`)
- Use PascalCase for component files (e.g., `AuthWizard.tsx`)
- Use camelCase for utility files (e.g., `formatDate.ts`)

### Component Organization
```typescript
// Order within a component file:
// 1. Imports
// 2. Types/Interfaces
// 3. Constants
// 4. Helper functions
// 5. Main component
// 6. Subcomponents
// 7. Export

import { useState } from 'react'
import type { Post } from '@/types'

interface PostCardProps {
  post: Post
  onLike?: (id: string) => void
}

const MAX_TITLE_LENGTH = 100

function truncateTitle(title: string) {
  return title.length > MAX_TITLE_LENGTH
    ? `${title.slice(0, MAX_TITLE_LENGTH)}...`
    : title
}

export function PostCard({ post, onLike }: PostCardProps) {
  // Component logic
}
```

## Optimization Guidelines

### Minimize Client-Side JavaScript
- Minimize the use of `'use client'`, `useEffect`, and `useState`
- Favor React Server Components (RSC) and Next.js SSR features
- Use dynamic imports for code splitting

```typescript
// Dynamic import for heavy components
const HeavyChart = dynamic(() => import('@/components/HeavyChart'), {
  loading: () => <ChartSkeleton />,
  ssr: false,
})
```

### Image Optimization
- Use Next.js Image component with proper sizing
- Use WebP format when possible
- Implement lazy loading for below-fold images

```typescript
import Image from 'next/image'

<Image
  src="/hero.webp"
  alt="Hero image"
  width={1200}
  height={600}
  priority // Only for above-fold images
  className="object-cover"
/>
```

### Mobile-First Responsive Design
```typescript
// Tailwind mobile-first approach
<div className="px-4 md:px-6 lg:px-8">
  <h1 className="text-xl md:text-2xl lg:text-3xl">
    Responsive heading
  </h1>
</div>
```

## Error Handling Patterns

### Early Returns and Guard Clauses
```typescript
export async function getPost(id: string) {
  // Guard clause - validate input early
  if (!id) {
    throw new Error('Post ID is required')
  }

  const supabase = await createClient()

  const { data, error } = await supabase
    .from('posts')
    .select()
    .eq('id', id)
    .single()

  // Early return on error
  if (error) {
    throw new DatabaseError('Failed to fetch post', { cause: error })
  }

  // Early return on not found
  if (!data) {
    throw new NotFoundError('Post not found')
  }

  return data
}
```

### Custom Error Types
```typescript
// lib/errors.ts
export class AppError extends Error {
  constructor(
    message: string,
    public code: string,
    public statusCode: number = 500
  ) {
    super(message)
    this.name = 'AppError'
  }
}

export class NotFoundError extends AppError {
  constructor(message: string) {
    super(message, 'NOT_FOUND', 404)
    this.name = 'NotFoundError'
  }
}

export class ValidationError extends AppError {
  constructor(message: string) {
    super(message, 'VALIDATION_ERROR', 400)
    this.name = 'ValidationError'
  }
}
```

## State Management

### Use Zustand for Global State
```typescript
// stores/use-user-store.ts
import { create } from 'zustand'

interface UserState {
  user: User | null
  isLoading: boolean
  setUser: (user: User | null) => void
  setLoading: (loading: boolean) => void
}

export const useUserStore = create<UserState>((set) => ({
  user: null,
  isLoading: true,
  setUser: (user) => set({ user }),
  setLoading: (isLoading) => set({ isLoading }),
}))
```

### Use TanStack Query for Server State
```typescript
// hooks/use-posts.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

export function usePosts() {
  return useQuery({
    queryKey: ['posts'],
    queryFn: fetchPosts,
    staleTime: 5 * 60 * 1000, // 5 minutes
  })
}

export function useCreatePost() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: createPost,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['posts'] })
    },
  })
}
```

## Validation with Zod

```typescript
// lib/validations/post.ts
import { z } from 'zod'

export const createPostSchema = z.object({
  title: z.string().min(1, 'Title is required').max(200),
  content: z.string().min(1, 'Content is required'),
  published: z.boolean().default(false),
})

export type CreatePostInput = z.infer<typeof createPostSchema>

// Usage in Server Action
export async function createPost(input: unknown) {
  const validated = createPostSchema.parse(input)
  // ... proceed with validated data
}
```

## Documentation Standards

### JSDoc for Functions
```typescript
/**
 * Fetches a paginated list of posts for a user.
 * @param userId - The ID of the user
 * @param options - Pagination options
 * @returns Paginated posts with metadata
 * @throws {NotFoundError} If user doesn't exist
 */
export async function getUserPosts(
  userId: string,
  options: PaginationOptions = {}
): Promise<PaginatedResponse<Post>> {
  // Implementation
}
```

### Component Props Documentation
```typescript
interface ButtonProps {
  /** The button variant style */
  variant?: 'primary' | 'secondary' | 'ghost'
  /** Whether the button is in a loading state */
  isLoading?: boolean
  /** Click handler */
  onClick?: () => void
  /** Button contents */
  children: React.ReactNode
}
```
