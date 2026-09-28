# Queues and background work

## `retry_after` must exceed every job's `timeout`

```php
class ProcessReport implements ShouldQueue
{
    public $timeout = 120;
}
// config/queue.php  retry_after => 180   correct
// config/queue.php  retry_after => 90    wrong — the job is re-dispatched while still running
```

Why this is the first thing to check when "the job ran twice": the worker releases a job back to
the queue after `retry_after` seconds regardless of whether it is still executing. A charge, an
email or an inventory decrement then happens twice, with no error anywhere. Set `retry_after` above
the longest `timeout` in the codebase, not above the average.

## Back off exponentially

```php
public $tries = 3;
public $backoff = [1, 5, 10];
```

Default retries fire immediately, so a job failing because a third party is overloaded retries
three times inside a second and adds to the overload.

## Make jobs idempotent, and say so

A queued job will run more than once eventually — a worker restart, a deploy mid-job, a timeout.
Either the operation is naturally idempotent (`updateOrCreate`, setting a state) or it needs a
guard:

```php
class GenerateInvoice implements ShouldQueue, ShouldBeUnique
{
    public $uniqueFor = 3600;

    public function uniqueId(): string { return (string) $this->order->id; }
}
```

`ShouldBeUnique` holds the lock until the job finishes. `ShouldBeUniqueUntilProcessing` releases it
when processing starts — use that when a new request arriving mid-run should be queued rather than
dropped (search reindexing, cache rebuilds).

## Jobs carry identifiers, not state

`SerializesModels` stores the model's key and re-fetches on run. That is correct, and it means the
job sees the row **as it is when it runs**, not as it was when dispatched — including deleted. Guard
for the missing case rather than assuming the model resolves:

```php
public function handle(): void
{
    $order = Order::find($this->orderId);
    if ($order === null || $order->isCancelled()) {
        return;   // the world moved on; this is not an error
    }
}
```

Never pass a request, a closure, or an unserialisable service into a job's constructor.

## Always implement `failed()`

```php
public function failed(?Throwable $e): void
{
    $this->report->update(['status' => ReportStatusEnum::Failed]);
    Log::error('Report generation failed', ['report_id' => $this->report->id, 'error' => $e?->getMessage()]);
}
```

Without it, a record sits in `processing` forever and the user sees a spinner with no explanation.

## Rate-limit jobs that call third parties

```php
public function middleware(): array
{
    return [new RateLimited('external-api')];
}
```

A queue drains as fast as workers allow, which is exactly how a backlog of 5,000 jobs gets an API
key suspended.

## Batches for work that succeeds or fails together

```php
Bus::batch([new ImportChunk($a), new ImportChunk($b)])
    ->then(fn (Batch $b) => $user->notify(new ImportComplete))
    ->catch(fn (Batch $b, Throwable $e) => Log::error('Import batch failed', ['batch' => $b->id]))
    ->dispatch();
```

## Time-based retries need `$tries = 0`

```php
public $tries = 0;

public function retryUntil(): DateTimeInterface { return now()->addHours(4); }
```

Leave `$tries` at its default and the job stops after three attempts regardless of the deadline.

## Queueable Actions

Where the repo uses `spatie/laravel-queueable-action`, the same Action class runs synchronously
(`$action->execute(...)`) or on a queue (`$action->onQueue()->execute(...)`). Decide at the call
site, not by writing a second class. The Action's constructor dependencies are resolved from the
container on the worker, so they must be resolvable there — an Action injecting something bound
only in an HTTP middleware will fail only once it is queued.

## Queues and priorities

Name queues by latency requirement, not by feature: `high`, `default`, `low`. A feature-named queue
means adding a feature requires a worker config change, which is how jobs end up on a queue nothing
consumes.

Horizon earns its place once you need per-queue autoscaling, failure visibility or metrics:

```php
'supervisor-1' => [
    'connection' => 'redis',
    'queue' => ['high', 'default', 'low'],
    'balance' => 'auto',
    'minProcesses' => 1,
    'maxProcesses' => 10,
    'tries' => 3,
],
```

Check that a deployed change to job class names or namespaces is backwards-compatible with jobs
already sitting in the queue — a payload referencing a class that no longer exists fails on every
retry until it is flushed by hand.

## `defer()` instead of a job for trivial work

Post-response logging, analytics, cache warming: `defer(fn () => ...)` runs after the response in
the same process, with no queue round-trip. Use a job only when the work must survive a crash.
