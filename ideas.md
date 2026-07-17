## Ideas
1. 

/btw add 2. add text to speech 

3. Pop up Chatbot Chrome Extention Functionality 
    3b. Gets context from the screen using screenshots and is able to explain / fix Forms / Buisness Rules/ Reports  by making copies directly using epm automate or in the chat popup showing the solution 
    3c. Can look at excel files and see the macros and larger context in detail and explain / remake the form  this when you are done and any other functionality you feel is neccecary 


## Ideas idk if they are implemented yet
1. Skills over overview and section tab + add skill functionality 
2. 

## Queued / status (2026-07-17)
- [x] **2. Artifact support for Forms + Report View** — backend + frontend done & tested. Report engine (smart formatting, per-cell/table/artifact prompt edits, HTML/CSV/JSON/MD downloads, `/api` routes) + Claude-style artifacts panel wired into the shell (top-right toggle, Form/Report + Edit tabs, inline cell/table prompts, download). Forms & reports both openable.
- [x] **EPM Automate skill** — `EpmAutomateSkill` + `epm_automate/SKILL.md` wired into the wizard (intent + `/epm-automate` slash, risk classification, destructive-op confirmation).
- [x] **Text-to-speech** — `frontend/src/tts/`: per-message read-aloud button + header auto-speak toggle (voice + speed), browser Web Speech API (offline, no keys). Markdown stripped for clean speech.

## Notes
Type **docker compose up --build** to run in terminal 




## Future IBM Support ideas 
1. Cerebras - for ai training and fast inference ??? 