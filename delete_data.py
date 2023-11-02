import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import datetime

# スプレッドシートの古い内容を削除する関数
def delete_old_content():
    creds = None
    # トークンの読み込み
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json')
    service = build('sheets', 'v4', credentials=creds)

    # スプレッドシートIDを指定
    SPREADSHEET_ID = 'YOUR_SPREADSHEET_ID'
    RANGE_NAME = 'A1:E'  # 適切な範囲を指定

    # 現在の時刻を取得
    now = datetime.now()

    try:
        # スプレッドシートのデータを取得
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        values = result.get('values', [])

        # 古いデータを削除
        new_values = [row for row in values if datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") > now - timedelta(days=7)]
        body = {'values': new_values}
        result = service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME,
            valueInputOption='RAW', body=body).execute()
    except Exception as e:
        print(f"Error in deleting old content: {e}")
        traceback.print_exc()