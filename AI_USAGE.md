# AI-assisted development

**Tool:** ChatGPT Work coding assistant. **Model:** GPT-6.1.
AI assisted with the implementation, tests, code review and documentation.
The finished app itself does not call any AI service or require API keys.

## Input examples

The job specification was supplied as context, including:

> Создайте с нуля небольшое веб-приложение для учёта рабочего времени сотрудников компании.

> Добавьте проверки основных сценариев, включая повторный запуск таймера и пустой отчёт.

Follow-up requests from the applicant included:

> можно как будто покрасивше получше сделать)

> а по тз не требуется чтобы была отдельная часть с трекером для сотрудника отдельно связанным с общим? я бы сделал поидее

These are actual input excerpts, not reconstructed prompts. The first two
come from the employer's specification. Initial stack selection, implementation
and test design were assistant-led. The applicant tried the original version,
requested the UI and personal-tracker changes, and reviewed the database
uniqueness and interval-overlap decisions in conversation.

## Issues found in generated code

| Finding | Correction | Verification |
| --- | --- | --- |
| Focus refresh discarded unsent task descriptions. | Preserve drafts by employee ID; restore input focus/selection on the dashboard. | Code review; final browser check pending. |
| Older report responses could overwrite newer selections. | Ignore stale responses using request sequence numbers. | Code review; final browser check pending. |
| Live counters depended on the browser's wall clock. | Anchor to server time and advance with `performance.now()`. | HTTP state test and code review; visual check pending. |
| Employee and entry reads could observe different database states. | Use a shared read-transaction snapshot. | Code review; the race was not reproduced by a failing test. |
| A failed refresh could make a successful write look like a failed mutation. | Report write success separately from the following screen refresh. | Code review; final browser check pending. |
| A submitted personal task could remain as the next task's draft. | Clear the submitted draft before refreshing personal state. | Code review; final browser check pending. |

Concurrent starts, repeated stops and period clipping were protected during
implementation and tested; they are not presented as bugs discovered by a
previously failing test. No fabricated debugging history is included.

## Validation

- 16 Python domain/HTTP tests pass locally on Python 3.12.14.
- Both browser JavaScript files pass Node syntax checks.
- The applicant manually tried the first version. A complete checklist of that
  run was not recorded.
- Final browser/visual verification remains pending: the build runtime had no
  Chromium, its download failed, and the separate browser could not reach the
  local app. API tests do not establish that browser interactions passed.
- GitHub Actions is configured; no CI result is claimed before publication.
