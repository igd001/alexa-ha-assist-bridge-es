# Alexa ↔ Home Assistant Assist Bridge

A tiny **Alexa custom skill** that turns your Echo devices into a two‑way voice interface for **Home Assistant Assist**.

Unlike the native Alexa smart‑home integration (limited to Amazon's grammar), this bridge lets you:

- **Ask questions from Home Assistant** — HA can make an Echo *proactively* speak a question (e.g. *"Should I close the shutters?"*) and wait for your answer.
- **Answer with `yes` / `no` or custom intents** — your reply is routed into `conversation.process`, so **any HA automation with a `conversation` trigger** reacts.
- **Whisper** — questions can be whispered (`<amazon:effect name="whispered">`) for discreet late‑night prompts.
- **Free speech** — say anything after opening the skill; it goes straight to Assist.

It is essentially *Alexa Actionable Notifications*, but built on top of Assist — so it's open, unlimited in the number of responses, and 100 % driven by your own HA automations.

---

## How it works

```
Home Assistant                         Alexa
──────────────                         ─────
script.poser_question_alexa
  ├─ writes the question to
  │  input_text.assist_alexa_question   (JSON: {t,y,n,w})
  └─ toggles
     input_boolean.declencher_...       (exposed to Alexa)
                                        │
                                        ▼  (Alexa Routine)
                                  "open my assistant"  ──► Skill LaunchRequest
                                                             ├─ reads the question from HA
                                                             ├─ speaks it (optionally whispered)
                                                             └─ keeps the mic open
        conversation.process  ◄──  you say "yes" / "no" / …
        (your conversation‑trigger automation runs and answers)
```

- `LaunchRequest` → the skill `GET`s `input_text.assist_alexa_question`, speaks the `t` text, stores the `y`/`n`/whisper values in the session.
- `AMAZON.YesIntent` / `AMAZON.NoIntent` / custom intents → the skill `POST`s the matching phrase to `/api/conversation/process`; whatever HA returns is spoken back.
- Home Assistant clears the question after ~25 s (so the skill only makes **one** fast call).

---

## Repository layout

```
lambda/
  lambda_function.py      # the skill code (ASK SDK, Python)
  requirements.txt
skill-package/
  interactionModels/custom/fr-FR.json   # invocation name + intents (French)
home-assistant/           # example HA helpers, script and automations
```

---

## Setup

### 1. Home Assistant

Create the helpers and script (see `home-assistant/` for full YAML):

- `input_text.assist_alexa_question` — holds the pending question (max length **255**).
- `input_boolean.declencher_question_alexa` — the trigger, **exposed to Alexa**.
- `script.poser_question_alexa(text, yes_command, no_command, echo, whisper)` — fills the helper, sets the Echo volume, toggles the trigger, then clears the helper after 25 s.
- Create one **`conversation`‑triggered automation per answer** (e.g. commands `["yes, ...", "..."]`) that does the action **and** replies via `set_conversation_response`.

> ⚠️ If an answer runs a **slow script** (retries/delays), call it with `script.turn_on` (fire‑and‑forget), not `action: script.x`. Otherwise `conversation.process` exceeds the skill's 4 s timeout and Alexa says *"I couldn't reach…"* even though the action ran.

Generate a **Long‑Lived Access Token**: HA → your profile → **Security** → *Long‑lived access tokens*.

### 2. Alexa Developer Console

1. Go to <https://developer.amazon.com/alexa/console/ask> (sign in with the **same Amazon account as your Echo devices**).
2. **Create Skill** → name it, primary locale **French (FR)** → model **Custom** → host **Alexa‑hosted (Python)**.
3. **Build** tab → *Interaction Model → JSON Editor* → paste `skill-package/interactionModels/custom/fr-FR.json` → **Save** → **Build Skill**.
4. **Code** tab → paste `lambda/lambda_function.py`, then edit the two constants at the top:
   ```python
   HA_URL   = "https://YOUR_HA_URL.ui.nabu.casa"
   HA_TOKEN = "YOUR_LONG_LIVED_ACCESS_TOKEN"
   ```
   Paste `lambda/requirements.txt` too → **Save** → **Deploy**.

> **CLI alternative** (recommended for iterating): `npm i -g ask-cli`, `ask configure`, then `ask init --hosted-skill-id <id>` to clone. Deploy a hosted skill with `git push origin master` (master → *development* stage). Test with `ask smapi simulate-skill` or locally with a mock event.

### 3. Alexa app — the Routine (this is what makes HA able to talk to you)

Amazon does not let HA make an Echo *ask + listen* on its own, so a Routine launches the skill when HA raises the trigger:

1. Open the **Alexa app** → **More → Routines → +**.
2. **Name**: e.g. `House question`.
3. **When this happens** → **Smart Home** → pick **`Declencher Question Alexa`** (the exposed `input_boolean`) → *turns On / opens*.
   *If Alexa won't let a switch be a trigger, expose a `binary_sensor` (device_class `motion`/`contact`) mirroring the boolean instead.*
4. **Add action** → **Custom** → type the skill invocation, e.g. `open my assistant`.
5. Choose the **Echo device** the routine should run on (where the question is asked).
6. **Save**.

> ⚠️ **Invocation name** must not collide with an existing Routine phrase or a smart‑home group name. `"open the house"` may trigger *your* shutters instead of the skill — pick something distinctive.

---

## Usage

From any HA automation:

```yaml
- action: script.poser_question_alexa
  data:
    text: "You are turning off the TV and the shutters are open. Should I close them?"
    yes_command: "close the shutters"     # matches a conversation‑trigger automation
    no_command: "leave the shutters open"
    echo: media_player.your_echo
    whisper: true                          # optional
```

Then two `conversation`‑triggered automations handle `"close the shutters"` and `"leave the shutters open"`. Add as many intents/answers as you like — that's the whole point.

---

## Notes for developers

- **ask‑sdk handler parameter must be named `handler_input`** (and the exception handler `(handler_input, exception)`). The framework calls handlers by keyword, so `def can_handle(self, h)` raises `TypeError` → the skill returns an invalid response and Alexa says *"there was a problem with the requested skill"*.
- Custom intent samples that contain the word *"no"* may be grabbed by `AMAZON.NoIntent` — keep phrasings distinct.
- The whispered SSML effect does **not** render in the Developer Console simulator, but works on a real Echo.

## License

MIT — do whatever you want.
