import os
import json
import requests
import traceback
from langchain.document_loaders import HNLoader
from langchain.chat_models import ChatOpenAI
from langchain.chains import create_extraction_chain
import openai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from datetime import datetime
import time
import base64
from bs4 import BeautifulSoup

# スプレッドシートから前回のニュースIDを取得する関数
def get_last_checked_id_from_sheet(service, SPREADSHEET_ID):
    RANGE_NAME = 'J1'  # 最新記事IDが保存されるセル
    result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
    values = result.get('values', [])
    if not values:
        return None
    return values[0][0]

# スプレッドシートに最新のニュースIDを保存する関数
def update_last_checked_id_on_sheet(service, SPREADSHEET_ID, new_id):
    RANGE_NAME = 'J1'  # 最新記事IDを保存するセル
    values = [[new_id]]
    body = {'values': values}
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME,
        valueInputOption='RAW', body=body).execute()

# エンコードされた認証情報を取得
encoded_creds = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
if not encoded_creds:
    raise ValueError("環境変数 'GOOGLE_APPLICATION_CREDENTIALS_JSON' が設定されていません。")
# base64デコード  
decoded_creds = base64.b64decode(encoded_creds)

# JSONロード
service_account_info = json.loads(decoded_creds)

# Credentialsインスタンス作成
credentials = service_account.Credentials.from_service_account_info(
  service_account_info,
  scopes=[
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
  ]
)

# Sheets APIのserviceインスタンスを作成
service = build('sheets', 'v4', credentials=credentials)

# スプレッドシートのIDを取得
SPREADSHEET_ID = os.getenv('YOUR_SPREADSHEET_ID')
if not SPREADSHEET_ID:
    raise ValueError("環境変数 'YOUR_SPREADSHEET_ID' が設定されていません。")


# OpenAI APIキーを環境変数から取得
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("環境変数 'OPENAI_API_KEY' が設定されていません。")

# スキーマを定義
schema = {
    "properties": {
        "category1": {"type": "string"},
        "category2": {"type": "string"},
        "category3": {"type": "string"},
    },
    "required": ["category1"]
}


def openai_api_call(model, temperature, messages):
    try:
        response = openai.ChatCompletion.create(
            model=model,
            temperature=temperature,
            messages=messages
        )
        return response.choices[0].message['content']
    except openai.OpenAIError as e:  
        print(f"OpenAI API error: {e}")
        traceback.print_exc()
        return None
    except Exception as e:
        print(f"Error in OpenAI API call: {e}")
        traceback.print_exc()
        return None


# カテゴリー作成関数
def generate_category(content):
    try:
        # LLM (Language Model) を初期化
        llm = ChatOpenAI(temperature=0, model="gpt-3.5-turbo")
        # 抽出チェーンを作成
        chain = create_extraction_chain(schema, llm)
        # チェーンを実行
        extracted_categories = chain.run(f"あなたは優秀なカテゴリ生成アシスタントです。提供された文章をもとに、カテゴリ(2個から3個)を生成してください。\n\n{content}")
        return extracted_categories
    except Exception as e:
        print(f"Error in category generation: {e}")
        traceback.print_exc()
        return "カテゴリを生成できませんでした"

# リード文作成関数
def generate_lead(content):
    try:
        lead = openai_api_call(
        "gpt-3.5-turbo-0613",
        0.6,
        [
            {"role": "system", "content": "あなたは優秀なリード文生成アシスタントです。提供された文章をもとに、日本語のリード文を生成してください。"},
            {"role": "user", "content": content}
        ]
    )
        return lead
    except Exception as e:
        print(f"Error in lead generation: {e}")
        traceback.print_exc()
        return "リード文を生成できませんでした"


# 要約用の関数
def summarize_content(content):
    try:
        summary = openai_api_call(
        "gpt-3.5-turbo-16k-0613",
        0,
        [
            {"role": "system", "content": "あなたは優秀な要約アシスタントです。提供された文章をもとに、できる限り正確な内容にすることを意識して要約してください。"},
            {"role": "user", "content": content}
        ]
        )
        return summary
    except Exception as e:
        print(f"Error in summarization: {e}")
        traceback.print_exc()
        return "要約できませんでした"


# 意見生成用の関数
def generate_opinion(content):
    try:
        opinion = openai_api_call(
        "gpt-4",
        0.6,
        [
            {"role": "system", "content": "あなたは優秀な意見生成アシスタントです。提供された文章をもとに、文章に関する感想や意見を生成してください。"},
            {"role": "user", "content": content}
        ]
        )
        return opinion
    except Exception as e:
        print(f"Error in opinion generation: {e}")
        traceback.print_exc()
        return "意見を生成できませんでした"


# スプレッドシートへの書き込み関数
def write_to_sheet(service, SPREADSHEET_ID, summary, opinion, categories, lead, new_id):
    RANGE_NAME = 'A1'  # 要約と意見が書き込まれる範囲の開始セル
    # 現在の時刻を取得
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # データの書き込み
    values = [[now, summary, opinion, ", ".join(categories), lead]]
    body = {'values': values}
    # 要約と意見をスプレッドシートに追記
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME,
        valueInputOption='RAW', body=body).execute()
    # 最新の記事IDをJ1セルに書き込む
    update_last_checked_id_on_sheet(service, SPREADSHEET_ID, new_id)


# 新しいHacker Newsのコンテンツを確認する関数
def check_new_hn_content(request):
    # service インスタンスと SPREADSHEET_ID を取得
    service = build('sheets', 'v4', credentials=credentials)
    SPREADSHEET_ID = os.getenv('YOUR_SPREADSHEET_ID')

    # 最後にチェックしたIDを取得
    last_checked_id = get_last_checked_id_from_sheet(service, SPREADSHEET_ID)
    try:
        # Hacker Newsのトップページをロード
        loader = HNLoader("https://news.ycombinator.com/")
        data = loader.load()

        # トップニュースのIDを取得
        new_id = data[0]['id']

        # 新しいニュースがあるか確認
        if new_id != last_checked_id:
            # 新しいニュースの内容をすべて取得
            full_content = data[0]['page_content']

            # 内容を要約
            summary = summarize_content(full_content)

            # 意見を生成
            opinion = generate_opinion(summary)

            # リード文を生成
            lead = generate_lead(summary)

            # カテゴリを生成
            categories = generate_category(full_content)

            # スプレッドシートに要約と意見を書き込む
            write_to_sheet(service, SPREADSHEET_ID, summary, opinion, categories, lead, new_id)

            # 最後に確認したニュースのIDを更新
            update_last_checked_id_on_sheet(service, SPREADSHEET_ID, new_id)
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
    except openai.OpenAIError as e: 
        print(f"OpenAI API error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        traceback.print_exc()
