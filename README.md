### web-page

configure python project using

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

create `.env` with following contents:
```.env
SECRET_KEY=...

YANDEX_CLIENT_ID=...
YANDEX_CLIENT_SECRET=...

GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

TARGET="REMOTE"
REMOTE_ADDRESS="your.domain.com"

DATABASE_URI=sqlite:///instance/site.db
```

1. generate `SECRET_KEY` using `python3 -c "import secrets; print(secrets.token_hex(32))"`
2. get `YANDEX_CLIENT_ID` and `YANDEX_CLIENT_SECRET` from https://oauth.yandex.ru
3. get `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` from https://console.cloud.google.com
4. run app using `./app.py`

`TARGET=LOCAL` for development on localhost or `TARGET=REMOTE` for deployment on a `REMOTE_ADDRESS`

