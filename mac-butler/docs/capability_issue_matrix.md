# Capability Issue Matrix

Working log of user-reported failures to convert into planner coverage, tool wiring, and regression tests.

## Routing And Tool Selection

- Natural phrasing should work without trigger words like `search`, `open`, or `compose`.
- `check my vps` routes to `unknown` instead of checking the VPS.
- `minimize this window` does not reach the existing `minimize_app` executor path.
- `play <song> on youtube` incorrectly routes to Spotify.
- `not on spotify, play it on youtube` loses source/provider intent.
- `search weather in mumbai` and similar weather phrasing fail.
- `president of america` and similar current-fact questions fail.
- `make one more folder on desktop with name ...` must create on Desktop, not default to `~/Developer`.
- `create a folder on desktop with name ...` previously created the wrong nested path and must stay pinned as a regression case.
- `tell me my pending task` and `check calendar` should resolve without exact command wording.
- `open calendar`, `add new event`, `send invites`, `send whatsapp messages`, and `write an email` need natural-language coverage.
- `tell me what project I worked on yesterday`, `what's completed`, and `what was done yesterday` need resolved lookup paths.
- `tell me my pending task can u check calender` and `check calender and tell me my meetings` are explicit failing live phrases.
- `how much time will you think about this` should behave like normal conversation, not fail or go blank.
- `open gmail and write a mail to vedang2803@gmail.com with subject test gmail and body how are u` must parse the subject/body cleanly.
- `with subject hello` after an email draft currently routes to `unknown` because pending dialogue only supports song/file follow-ups.
- `write mail to vedang2803 at the red gmail com ...` currently truncates the recipient before email normalization.
- `open terminal` currently uses the generic app-open path and can duplicate Terminal windows on cold launch.
- Volume and browser-tab controls exist in code, but their user-visible coverage needs explicit semantic routing and regression tests.
- WhatsApp send exists in code, but `send whatsapp to vedang ...` currently parses the contact as `to vedang` and often only opens WhatsApp Web.

## Conversation Quality

- Butler should speak naturally like a normal chatbot when no tool is needed.
- Butler should understand intent from messy phrasing, not just narrow commands.
- Responses like `I didn't catch that. Say open, search, compose mail, or latest news.` must be removed.
- Responses like `I don't know yet. Ask again in a shorter way.` must be removed.
- Butler should address the user as `sir` consistently if that persona is desired.
- Butler should handle brainstorming/help-me-think prompts conversationally.
- Conversation memory currently exists mostly as prompt context, not as executable slot state, so commands still feel isolated.

## Lookup / Research Behavior

- News/weather/current facts should return one final spoken answer, not just an acknowledgement.
- `latest ai news` should not silently queue background work with no final reply.
- Topic news like `latest news on Claude Mythos` must complete as a real turn, not a fire-and-forget background job.
- Calendar access appears inconsistent between skills/toolkit/runtime pipeline and must be verified.
- AgentScope/toolkit availability must match what the user can actually trigger from voice/HUD.
- Low-signal fallback replies are currently leaking into recall, RL, and long-term memory and must not be learned.
- Startup briefing currently exists only as a recent-session/project summary and does not include GitHub pushes, weather, or calendar.

## Voice And Runtime

- Mic hold / long-press behavior is unreliable.
- Butler is missing or truncating longer spoken input.
- TTS quality is too weak; evaluate a stronger medium-quality voice model beyond Kokoro.
- Voice session should feel live and context-aware, including pending tasks, weather, and project activity.

## Testing Requirements

- Every phrase above should become an explicit regression test.
- Tests must cover semantic planning, resolver behavior, tool selection, and preserved executor actions.
- Tests must include natural-phrase variants, not just canonical command strings.
