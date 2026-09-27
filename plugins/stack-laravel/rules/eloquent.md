# Eloquent

## Relationships carry return types

```php
public function comments(): HasMany { return $this->hasMany(Comment::class); }
public function author(): BelongsTo { return $this->belongsTo(User::class, 'user_id'); }
```

Untyped relationship methods defeat larastan's ability to infer the related model, which silently
weakens every static check downstream of the relation.

## Local scopes over repeated `where` chains

```php
// Wrong — the same definition of "active" drifts between the two call sites
User::where('verified', true)->whereNotNull('activated_at')->get();
Article::whereHas('user', fn ($q) => $q->where('verified', true)->whereNotNull('activated_at'))->get();

// Right
public function scopeActive(Builder $query): Builder
{
    return $query->where('verified', true)->whereNotNull('activated_at');
}
```

Scopes are also what filter packages hook into (`AllowedFilter::scope('search', 'search_by_name')`),
so a scope is reusable from the query layer for free.

## Global scopes only for truly universal constraints

Soft deletes and tenancy qualify. A "published" filter does not.

```php
// Wrong — admin panels, exports and background jobs now silently skip drafts,
// and the omission is invisible at every call site
class PublishedScope implements Scope { /* where('published', true) */ }

// Right — opt in
Post::published()->paginate();   // storefront
Post::paginate();                // admin sees everything
```

## Casts

Declare every date, boolean, JSON, decimal and enum column.

```php
protected function casts(): array
{
    return [
        'is_active' => 'boolean',
        'metadata'  => 'array',
        'total'     => 'decimal:2',
        'status'    => ProductStatusEnum::class,
        'ordered_at'=> 'datetime',
    ];
}
```

An uncast date column reaches the view as a string, which is how `Carbon::createFromFormat(...)`
calls end up scattered through templates. Follow the repo's existing choice between the `casts()`
method and the `$casts` property; do not mix both in one model.

## N+1 is the default failure mode

```php
// 1 + N queries
$posts = Post::all();
foreach ($posts as $post) { echo $post->author->name; }

// 2 queries
$posts = Post::with('author')->get();
```

Turn the failure into an exception during development, in `AppServiceProvider::boot()`:

```php
Model::preventLazyLoading(! app()->isProduction());
```

Without this, an N+1 introduced in a controller is invisible until a list grows in production.
Check jobs, API resources and DTO factories too — a `fromModel()` that touches a relation causes a
query per row inside `->through(...)`, which is the hardest N+1 to spot in review.

Count with `withCount()`, never by loading the collection:

```php
$posts = Post::withCount('comments')->get();   // $post->comments_count
```

## Select what you need, and always include the foreign key

```php
$posts = Post::select('id', 'title', 'user_id', 'created_at')
    ->with(['author:id,name,avatar'])
    ->get();
```

Drop `user_id` from the outer select and the eager load matches nothing, silently — the relation
returns null rather than erroring.

## Iterating large result sets

| Situation | Use |
| --- | --- |
| Read-only pass over many rows | `cursor()` — one model at a time via a generator |
| Processing in batches | `chunk(200, ...)` |
| Modifying or deleting rows while iterating | `chunkById(200, ...)` |

`chunk()` pages with `OFFSET`. If the loop body changes which rows match the `where`, later pages
shift underneath it and rows get skipped. `chunkById()` pages by primary key and is immune.

## Always order explicitly

Without `ORDER BY`, row order is undefined — PostgreSQL will happily return the same query in a
different order once the plan changes.

```php
Post::latest()->paginate();
```

## `whereBelongsTo()` over manual foreign keys

```php
Post::whereBelongsTo($user);            // instead of where('user_id', $user->id)
Post::whereBelongsTo($user, 'author');
```

## No hardcoded table names in application code

```php
// Wrong — renaming the table means grepping strings
DB::table('users')->where('active', true)->get();

// Right
User::where('active', true)->get();
DB::table((new User)->getTable())        // when the query builder is genuinely needed
```

Migrations are the exception and should hardcode: a migration is a frozen snapshot, and a model
referenced from it breaks the moment that model is renamed or deleted.

## Public identifiers

When a model has both an internal primary key and an external identifier (ULID/UUID), route
binding and every DTO expose the external one. Foreign keys and joins keep using the internal
integer key.

```php
public function getRouteKeyName(): string { return 'ulid'; }
```

Leaking a sequential primary key in a URL or a JSON payload tells any client how many records
exist and lets them walk the range.
