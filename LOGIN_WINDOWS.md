# Windows에서 네이버 로그인 세션 만들기

미니PC가 headless이거나 `.env`에 `HEADLESS=1`이 있어도 `manual_login.py`는 이를 무시하고 항상 보이는 브라우저를 엽니다.

PowerShell:

```powershell
git pull
.\.venv\Scripts\python.exe manual_login.py
```

브라우저가 열리면 네이버에 직접 로그인하고 2단계 인증/캡차까지 완료합니다. 로그인 완료가 감지되면 저장소 루트에 `storage_state.json`이 생성됩니다.

미니PC로 복사:

```powershell
scp .\storage_state.json <USER>@<MINIPC_IP>:~/blogbot/storage_state.json
ssh <USER>@<MINIPC_IP> "chmod 600 ~/blogbot/storage_state.json && cd ~/blogbot && .venv/bin/python run.py check"
```

`storage_state.json`은 로그인 세션이므로 공유하거나 Git에 커밋하면 안 됩니다. `.gitignore`에 포함되어 있습니다.
