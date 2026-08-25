# Windows Desktop App

`NaverBlogWriter.exe` is a portable Windows UI for on-demand draft creation.

## What it does

1. Enter any topic.
2. Collect web evidence using the existing ranked research pipeline.
3. Generate and quality-review the Korean blog post.
4. Collect relevant images.
5. Open Naver Blog editor through the saved browser session.
6. Save the result as a **draft only**.

The app intentionally has no live-publish button.

## First run

1. Run `NaverBlogWriter.exe`.
2. Open **설정**.
3. Enter the OpenCode Go API key and save.
4. Click **API 연결 테스트**.
5. Click **네이버 로그인** and complete Naver login in the browser once.
6. Return to **글 작성**, enter a topic, then click **글 작성 후 네이버 임시저장**.

## Persistent data

The app keeps settings, the Naver session, logs, and local images in:

`%LOCALAPPDATA%\NaverBlogWriter`

Replacing the portable EXE does not delete this folder.

## Build locally

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean NaverBlogWriter.spec
```

The portable build appears at:

`dist\NaverBlogWriter\NaverBlogWriter.exe`

The GitHub Actions workflow `Build Windows EXE` also produces a downloadable `NaverBlogWriter-Windows` artifact.
