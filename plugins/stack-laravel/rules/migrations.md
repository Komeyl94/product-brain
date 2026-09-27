# Migrations

Generate with `php artisan make:migration <name> --no-interaction` so the timestamp and class name
are right. Never hand-create the file.

## A merged migration is immutable

Once a migration is on the shared branch, never touch its `up()`/`down()` body — not even to fix a
bug in it. Write a new migration.

```php
// Wrong — editing 2026_07_28_000002_add_sku_scoping_to_specs_table.php after merge
// Right — 2026_08_01_000000_backfill_and_enforce_sku_id_on_specs.php
```

Why: teammates' databases, CI caches and staging have already recorded that migration name as run.
Editing the body means two environments execute different SQL under the same name, and nothing
records the divergence — you find out months later when a column exists in one place and not
another. Before editing anything under `database/migrations/`, check whether the file is still
local and unpushed.

## Never add a NOT NULL column or a foreign key in one step

`->constrained()` implies `NOT NULL` unless you chain `->nullable()`. Either fails instantly against
a table that already has rows — which includes every dev machine and staging, not just production.

```php
// Wrong — "column contains null values"
$table->foreignId('sku_id')->constrained('skus')->cascadeOnDelete();
```

Split across migrations:

```php
// 1 — add nullable
$table->foreignId('sku_id')->nullable()->constrained('skus')->nullOnDelete();

// 2 — backfill
DB::table('specs')->whereNull('sku_id')->update(['sku_id' => /* derived */]);

// 3 — tighten
$table->foreignId('sku_id')->nullable(false)->change();
```

Why it keeps happening: `migrate:fresh` starts at zero rows, so the single-step version always
looks correct locally. Before writing a non-nullable column addition, ask whether any environment
could already hold rows in that table. For any table older than the migration, assume yes.

## `down()` is required

Enforced by `laravel/migration-requires-down`. Rollback is what makes a failed deploy recoverable
and what lets CI reset between runs. For a genuinely irreversible change (a destructive backfill),
say so in a comment and require a forward-fix migration instead of faking a reverse.

## No `enum` columns

Enforced by `laravel/no-enum-column-in-migration`. Use `$table->string(...)` and let the PHP backed
enum plus validation enforce the allowed values.

```php
// Wrong — compiles to varchar + CHECK (status in ('active','inactive'))
$table->enum('status', array_column(StatusEnum::cases(), 'value'));

// Right
$table->string('status')->default(StatusEnum::Active->value);
```

Why: the `CHECK` constraint freezes today's cases into the database. Add or remove a case in PHP
and the two drift — the constraint either rejects a value the app considers valid, or keeps
accepting one the app has retired. Fixing it needs a follow-up migration that drops and re-adds the
constraint by name, and until that ships nothing tells you they disagree. One source of truth, in
PHP, cannot drift. The consequence is that **validation is now the only guard** — see
`validation.md` on `Rule::enum`.

## One concern per migration; never mix DDL and DML

```php
// Wrong — if the insert fails, the table exists and the migration is recorded as failed,
// leaving a state no rollback describes
Schema::create('settings', ...);
DB::table('settings')->insert([...]);
```

Separate `create_settings_table` and `seed_default_settings` migrations.

## Indexes belong in the migration that creates the column

Index every column that appears in `WHERE`, `ORDER BY`, `JOIN` or `GROUP BY`.

```php
Schema::create('orders', function (Blueprint $table) {
    $table->id();
    $table->foreignId('user_id')->constrained()->index();
    $table->string('status')->index();
    $table->timestampTz('created_at')->index();
    $table->index(['status', 'created_at']);   // composite for the common list query
});
```

- **Foreign keys are not auto-indexed.** PostgreSQL indexes the referenced side, not the
  referencing column. An unindexed FK means a sequential scan on every join and every cascade check.
- A composite index on `(a, b)` serves queries filtering on `a` alone, but not on `b` alone
  (leftmost rule). Order the columns by what you filter on first.
- `->unique(['a', 'b'])` creates the index as well — do not add a separate `->index()` for that pair.
- High-volume tables (audit logs, ledger entries, adjustments) need their primary timestamp column
  indexed or every time-range query becomes a full scan.

## PostgreSQL specifics

Many Laravel services run PostgreSQL; check `config/database.php` before assuming. Do not carry MySQL assumptions over.

```php
$table->timestampTz('created_at')->useCurrent();   // not timestamp() — PG is timezone-aware
$table->jsonb('metadata')->nullable();             // not json() — jsonb is indexable with GIN
```

Self-referencing foreign keys cannot be declared inside `Schema::create()`; the table does not yet
exist when the constraint is processed. Define the column, then constrain it:

```php
Schema::create('categories', function (Blueprint $table) {
    $table->id();
    $table->unsignedBigInteger('parent_id')->nullable()->index();
});

Schema::table('categories', function (Blueprint $table) {
    $table->foreign('parent_id')->references('id')->on('categories')->nullOnDelete();
});
```

Table names are plural. `->constrained()` pluralises the column stem to find the target table, so
`inventory_id` looks for `inventories` — verify the match rather than assuming.

Parent tables need an earlier filename timestamp than any child that references them; migrations
run in filename order, and a foreign key to a table that does not exist yet fails the deploy.

## Mirror database defaults in the model

```php
$table->string('status')->default('pending');   // migration
protected $attributes = ['status' => 'pending']; // model
```

Otherwise a freshly instantiated, unsaved model has `null` where every persisted row has `pending`,
and the difference surfaces only in whatever code path reads the attribute before saving.
