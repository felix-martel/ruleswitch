# ruleswitch-editor

Browse, edit and try a [ruleswitch](../README.md) policy in the browser, with one command:

```bash
uvx --from "git+https://github.com/felix-martel/ruleswitch#subdirectory=editor" ruleswitch-editor POLICY
```

POLICY is a profile directory, such as `examples/mallow/profiles/fr`. The page mirrors the policy's concepts: its
profile (context and principles), its structure, its turn and response axes and their values, its tiers and their
grids of cells, its prohibitions and its lexicons. Every id links to its definition and previews it on hover.

- **Document** reads the policy as people do.
- Each concept's page edits it with forms built from the profile's JSON Schema; a tier's grid opens a cell's form.
  The structure is read-only: edit `structure.yaml` and run `ruleswitch generate`.
- **Changes** compares the policy with git `HEAD`, article by article and line by line.
- **YAML** edits the files as text.
- The **Try** panel classifies a turn and a response, and shows the cell they land in, the nudge and the compliance.

Edits stay unsaved until **Save** (or Ctrl+S), which writes the files in place and keeps their comments.

The try panel classifies with `--classifier`, which reads its endpoint and key from the environment, as
`ruleswitch eval` does. OpenRouter serves both built-in classifiers:

```bash
export RULESWITCH_SYSTEMONE_URL=https://openrouter.ai/api RULESWITCH_SYSTEMONE_KEY=$OPENROUTER_API_KEY
ruleswitch-editor examples/mallow/profiles/fr --classifier systemone:liquid/d1-ultra --threshold alert=0.2 --threshold exit=0.5

export RULESWITCH_LLM_URL=https://openrouter.ai/api/v1 RULESWITCH_LLM_KEY=$OPENROUTER_API_KEY
ruleswitch-editor examples/three_laws/profiles/default --classifier judge:openai/gpt-5-mini
```

Without one, the panel takes the values set by hand.

The page is [Preact](https://preactjs.com) and [htm](https://github.com/developit/htm), vendored in
`static/vendor` (7 KB gzipped): there is no build step and nothing to install from npm.
