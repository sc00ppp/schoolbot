# Your files are the memory

SchoolBot keeps the useful parts of studying in a folder you control. The chat
is a place to work; saving the outcome is what makes the next chat useful.
SchoolBot doesn't read your chat accounts or automatically synchronize them.

## Rescue context from an existing chat

Paste this into the chat that already knows your coursework:

> Help me move my study context into local files. Write a concise Markdown
> handoff with: the course and goals; what I understand; what is confusing;
> assignments and deadlines I actually provided; code and filenames we used;
> unresolved errors; and concrete next steps. Clearly mark uncertainties.
> Include any important code that currently exists only in this chat. Do not
> invent deadlines, file contents, or progress. Separately draft a STATUS.md
> containing just my current state and next steps.

Create your course with `python schoolbot.py add-course python101`. Run
`python schoolbot.py session python101`, then paste the handoff into the printed
file. Save the drafted status to `school/courses/python101/STATUS.md`. Save code
as actual `.py` files in `assignments/` or `notes/`, so it doesn't remain trapped
in a handoff. Review the summary against the original conversation.

## Begin a study session

1. Update materials and run `python schoolbot.py ingest --course python101`.
2. Run `python schoolbot.py export python101`.
3. Open `school/exports/python101-context.md` and check the coverage section.
4. Attach that file to a new chat, or paste its contents. Attach original slides
   for diagrams and any relevant files listed in `python101-omissions.md`.
5. Give the tutor a concrete starting point:

> This file is my saved study context. Start with STATUS.md. I'm working on
> functions today. Ask me one question to check what I know, then guide me
> through the next step. Explain new terms and let me attempt the code first.

For a coding assistant with folder access, point it at the course folder and
ask it to read `STATUS.md`, `COURSE.md`, `TASKS.md`, and relevant materials.
For an ordinary web chat, you save its proposed edits yourself.

## End the session

> Draft a replacement STATUS.md and a short session handoff. Include what I
> learned, what we tried, which files changed, what failed, and exactly what
> to do next. Preserve unresolved questions. Suggest TASKS.md changes only for
> deadlines or progress we established in this session.

Run `python schoolbot.py session python101` and save the handoff in the new file.
Replace `STATUS.md` with the reviewed current state and update `TASKS.md`.
Re-export before switching chats or assistants. New exports include recent
session notes first; older notes and large materials may exceed the size budget.

## What belongs where?

| File / folder | Keep here |
| --- | --- |
| `STUDENT.md` | Your learning goals and explanation preferences |
| `COURSE.md` | Syllabus, term, topics, course rules |
| `STATUS.md` | Current understanding, blockers, immediate next steps |
| `TASKS.md` | Assignments, due dates, progress |
| `sessions/` | Dated summaries of what happened in chats |
| `notes/` | Durable explanations, saved chat summaries, practice code |
| `assignments/` | Instructions, your code, notebooks and working files |

Back up the entire `school/` folder. Exports are replaceable snapshots, not a
complete backup: they omit binary originals and may omit text over the budget.
Everything is local until you choose to share files with an AI service.
