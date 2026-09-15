# Documentation diagrams

The diagrams describe the current `QualityLoop` implementation, not measured model accuracy.
They are original vector artwork with fixed geometry, accessible descriptions, and no external
images, scripts or font downloads.

| Diagram | Purpose | Published in |
|---|---|---|
| `architecture-{en,zh}-{light,dark}.svg` | Scenario contracts, model roles, feedback loop, controlled output and runtime boundaries | English and Chinese READMEs |
| `decision-flow-{en,zh}-{light,dark}.svg` | Assessment, release/repair/fallback decisions, re-checks and exceptional termination | Architecture guide |

GitHub's `<picture>` markup selects a light or dark asset according to the reader's color
scheme. Full-size links remain available for inspecting the vector diagrams on smaller screens.
Adjacent documentation and alt text provide the textual explanation.

## Update

Edit labels, coordinates or palettes in [the renderer](../../scripts/render_diagrams.py),
then regenerate all eight assets from the repository root:

```bash
uv run python scripts/render_diagrams.py
uv run python scripts/render_diagrams.py --check
```

The renderer uses only Python's standard library. Generated SVGs are checked in so GitHub
does not need a rendering service. CI checks that the assets match the renderer.
Do not edit the generated SVGs by hand.
After changing geometry or text, inspect both languages and both themes in a browser:
check text bounds, line crossings, labels, contrast and scaled README readability.

## Design references

- [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents):
  a clear primary reading direction and a separate evaluator-optimizer feedback path.
- [AutoGen: Application stack](https://microsoft.github.io/autogen/dev/user-guide/core-user-guide/core-concepts/application-stack.html):
  layered responsibilities and restrained semantic colors.

These references informed the layout principles only. No reference artwork or logos are
embedded. VerifiGen's diagrams are covered by the repository's MIT license.
