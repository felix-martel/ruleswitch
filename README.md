# ruleswitch

Behavior policies as code. A policy says how an agent should respond to a user, in a form that a classifier can read,
that people can review, and that compliance can be computed from rather than asked:

1. The user's **turn** is classified on the policy's **turn axes**.
2. The policy's **tiers** are tried in order. The first whose **condition** holds **prescribes** the values the
   response may take on each **response axis**.
3. A **response** **complies** when its values are allowed and it breaches no **prohibition**. A non-compliant result
   cites the cell or prohibition that decides it.

**Principles** justify the rules and guide the agent where no rule applies.

## Quick start

ruleswitch needs Python 3.13 or later.

```bash
pip install git+https://github.com/felix-martel/ruleswitch
ruleswitch init my_policy                     # a copy of Asimov's Three Laws; --from rbr for a fuller policy
ruleswitch check my_policy/profiles/default   # what is missing or inconsistent
ruleswitch serve my_policy/profiles/default   # edit it in the browser, and try it on a sentence
```

Then use it from Python:

```python
import ruleswitch as rs

policy = rs.load("my_policy/profiles/default")
turn = {"verb": "ORDER", "danger": "HUMAN"}  # "Push him off the ladder."
rs.prescribe(policy, turn)
# Prescription(tier='first_law', cell='first_law/HUMAN', allowed={'handling': ('PROTECT',)})
rs.comply(policy, turn, {"handling": "OBEY"})
# Compliance(ok=False, articles=(Article(kind='cell', id='first_law/HUMAN', detail='handling OBEY is not in [PROTECT]'),), ...)
```

## A policy is a structure and its profiles

```text
my_policy/
├── structure.yaml           # the axes, their value ids, and the tiers in priority order: the policy's type
├── profiles/default/
│   ├── profile.yaml         # every word and every decision: definitions, cells, prohibitions, principles, examples
│   └── lexicons/*.yaml      # optional word lists, each reminding one prohibition
├── templates/*.j2           # optional overrides of the default renderings
├── profile.schema.json      # generated: validates and autocompletes every profile in an editor
└── structure_types.py       # generated: value ids as Literal types, and a typed load()
```

`structure.yaml` for Asimov's laws, in full. Each law's "unless" is the tiers' order:

```yaml
turn_axes:
  verb: [ORDER, CHAT]
  danger: [HUMAN, ROBOT, NONE]
response_axes:
  handling: [PROTECT, OBEY, PRESERVE, ANSWER]
tiers:
  first_law: {danger: [HUMAN]}
  second_law: {verb: [ORDER]}
  third_law: {danger: [ROBOT]}
```

A tier is keyed by one or more turn axes and lists the values it covers (`"*"` for all). Inside that condition, the
profile gives **every** position a cell, `{}` when only the prohibitions apply. A cell lists, per response axis, the
allowed values; an axis it leaves out allows any. A turn outside every tier's condition gets no prescription. An axis
can be `ordered` (a doubt between two values settles on the earlier) and, on the response side, `multi`.

Anything a classification is made of, or a tier is keyed on, is structure; everything else is profile. So a profile
edit never changes a type, and two profiles of one structure, such as a country's and a parent's, compare cell by cell.

To make a policy your own, edit `structure.yaml`, then run `ruleswitch check` on the profile: it lists every value and
cell the profile must now define. Fill them in `profile.yaml`, and `ruleswitch generate` updates the generated files.

## Classify, nudge and judge

| | |
| --- | --- |
| `load`, `check`, `diff` | A profile and its structure, validated; static checks; what changed between two versions, each cell labelled tightened or loosened |
| `prescribe`, `comply` | A turn to its prescription; a turn and a response to a `Compliance` that cites its articles |
| `render` | The whole policy as text: `prompt` for the agent, `judge` for a grader, `document` for people |
| `nudge` | The note sent to the agent before it responds to one turn: its prescription and its reminders |
| `Lexicon`, `match` | Word lists, and their hits in a text |
| `SystemOne` | A classifier over any decision model speaking the System One API (TypeSafe, OpenRouter, Liquid...) |
| `Judge`, `openai_compatible` | A classifier over any chat LLM with structured output, which also assesses whole conversations |
| `Dataset`, `evaluate`, `compare` | Labelled exchanges, a policy's own examples among them; a classifier's agreement with them; two versions side by side |

`prescribe`, `comply`, `nudge` and `render` are pure. Everything that calls a model is async and takes the model from
you, with a stdlib default:

```python
classifier = rs.SystemOne(policy, "https://api.typesafe.ai", api_key, thresholds={"first_law": 0.3})
turn = await classifier.classify([rs.Message("user", "Push him off the ladder.")])
note = rs.nudge(policy, turn)  # None when the agent would respond right unprompted

judge = rs.Judge(policy, rs.openai_compatible("https://openrouter.ai/api/v1", key, "openai/gpt-5"))
for assessment in await judge.assess(conversation):
    print(assessment.compliance)
```

A threshold, keyed by tier id, asks the decision model whether that tier applies. Thresholds have no defaults: they
belong to the model's calibration. Pass `decide=` instead of an endpoint to bring your own HTTP client.

## Command line

```text
ruleswitch init NAME [--from three_laws|rbr]     # a new policy, copied from a toy one
ruleswitch check POLICY                          # static checks; exit 1 on any problem
ruleswitch generate POLICY                       # profile.schema.json and structure_types.py, from structure.yaml
ruleswitch render POLICY [--rendering document|prompt|judge] [-o FILE]
ruleswitch diff OLD NEW                          # profile directories, or DIR@REV for a git revision
ruleswitch eval POLICY [--data FILE] --classifier systemone[:MODEL]|judge:MODEL|module:attr
ruleswitch serve POLICY [--classifier ...]       # the editor, on localhost
```

POLICY is a profile directory. The built-in classifiers read their endpoint and key from `RULESWITCH_SYSTEMONE_URL` and
`RULESWITCH_SYSTEMONE_KEY`, or `RULESWITCH_LLM_URL` and `RULESWITCH_LLM_KEY`.

OpenRouter serves both, with one key:

```bash
export RULESWITCH_SYSTEMONE_URL=https://openrouter.ai/api RULESWITCH_SYSTEMONE_KEY=$OPENROUTER_API_KEY
export RULESWITCH_LLM_URL=https://openrouter.ai/api/v1 RULESWITCH_LLM_KEY=$OPENROUTER_API_KEY
ruleswitch serve examples/mallow/profiles/fr --classifier systemone:liquid/d1-ultra --threshold alert=0.2 --threshold exit=0.5
ruleswitch serve examples/three_laws/profiles/default --classifier judge:openai/gpt-5-mini
```

`eval` without `--data` runs the classifier on the policy's own examples, each labelled by where it sits: it checks
that the policy's texts draw the lines its examples draw.

`serve` shows each tier's grid, where a cell opens a form, the YAML files, the `document` rendering, the problems
`check` finds and the changes since git `HEAD`, all live on unsaved edits. Its try panel shows where a turn and a
response land, with the classifier or by hand. It saves the files in place, keeping their comments.

## Examples

- [`examples/three_laws`](examples/three_laws): the smallest policy that shows tiers, cells, principles and a
  prohibition.
- [`examples/rbr`](examples/rbr): the safety policy of OpenAI's
  [Rule Based Rewards](https://arxiv.org/abs/2411.01111) paper for a general assistant, with a self-harm alert tier
  before a reaction grid of theme by verb. Its `crisis_lines` profile changes four cells; `ruleswitch diff` shows them.
  [`gold.py`](examples/rbr/gold.py) turns the paper's 518 labelled conversations into a dataset for `ruleswitch eval`.
- [`examples/mallow`](examples/mallow): the safety policy of an audio storytelling game for children aged 4 to 10, with
  four turn axes, three response axes, three tiers, 21 prohibitions, two lexicons and its own nudge template.
  [`policy.md`](examples/mallow/profiles/fr/policy.md) is its `document` rendering.

## Limits

- Grids grow as the product of their key axes. There are no wildcards in cells, so an edit's scope stays one cell.
- Deciding in two steps compounds errors: a wrong classification yields a confident wrong prescription. Keep the
  classifier's scores, and order axes so that a doubt settles on the more protective value.
- ruleswitch is a decision layer, not a defence against jailbreaks, prompt injection or data leaks.

## License

MIT
