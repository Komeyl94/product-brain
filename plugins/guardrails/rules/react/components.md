# React components

`react/no-class-component` blocks `extends Component` and `extends PureComponent` in
`.tsx` and `.jsx`.

It is gated on the repository: it fires only where the profile scan found **zero** class
components. So it is never a demand to migrate a legacy codebase — it fires when you are
about to be the first person to introduce a second component model into a codebase that
has exactly one.

## Why that is worth blocking

- Class components cannot use hooks. Every shared hook the app already has — `useAuth`,
  `useQuery`, `useTranslation`, the router hooks — needs a wrapper component or an HOC to
  reach a class, so one class component pulls a layer of adapters in behind it.
- Lifecycle methods and effects express the same intent differently. A reviewer switching
  between the two models makes more mistakes, and `componentDidUpdate` comparison bugs are
  a class of error the codebase currently does not have.
- Testing, memoisation and the Suspense/transition APIs all have a hook-shaped route and a
  worse or absent class-shaped one.

## What to write instead

```tsx
// wrong
class Counter extends React.Component<Props, State> {
  state = { count: 0 };
  componentDidMount() { this.props.onOpen(); }
  render() { return <button onClick={() => this.setState(s => ({ count: s.count + 1 }))}>{this.state.count}</button>; }
}

// right
function Counter({ onOpen }: Props) {
  const [count, setCount] = useState(0);
  useEffect(() => { onOpen(); }, [onOpen]);
  return <button onClick={() => setCount((c) => c + 1)}>{count}</button>;
}
```

Direct translations: `this.state` → `useState`, several related fields → `useReducer`,
`componentDidMount`/`componentWillUnmount` → `useEffect` with a cleanup return,
`PureComponent` → `React.memo`, `this.someRef` → `useRef`, an expensive `render`
computation → `useMemo`.

## Error boundaries are the real exception

React still has no hook equivalent for `componentDidCatch` /
`getDerivedStateFromError`. An error boundary must be a class.

Use `react-error-boundary` rather than writing one — it wraps the class and gives you a
hook-friendly API:

```tsx
<ErrorBoundary FallbackComponent={ErrorPanel} onReset={refetch}>
  <Dashboard />
</ErrorBoundary>
```

If the project cannot take the dependency, one hand-written boundary class is a legitimate
waiver — the single line, and a sentence in your reply saying it is an error boundary:

```tsx
class ErrorBoundary extends Component<Props, State> { // guardrail:allow error boundary, no hook equivalent exists
```

Note that adding a class component also flips the gate: once one exists, the rule stops
firing for everyone. That is another reason to keep it to the one boundary at the app
root rather than per feature.
