# Prompt Toolkit semantic color classes

## Failure pattern

Prompt Toolkit formatted-text fragments use a style string. When multiple style classes are combined, each class must carry the `class:` prefix:

```text
class:dashboard class:activity-meta
```

This is invalid and can raise:

```text
ValueError: Wrong color format 'activity-meta'
```

```text
class:dashboard activity-meta
```

Prompt Toolkit interprets the unprefixed second token as a foreground/color declaration rather than a class name.

## Safe extension pattern

- Preserve existing compatibility classes such as `state-pass`, `state-fail`, `state-running`, and `state-waiting`.
- Add new semantic classes as `activity-*` and `worker-*` in `Style.from_dict`.
- Emit them as `class:<base> class:<new-class>`.
- Build the application with the exact launcher interpreter and a `DummyOutput` probe; app construction exercises style parsing without requiring a live pseudoconsole.
- Run the focused layout/controller/hardening suite afterward.
