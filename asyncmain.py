import os
import requests
import traceback
from langchain.document_loaders import HNLoader
from langchain.chat_models import ChatOpenAI
from langchain.chains import create_extraction_chain
import openai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import asyncio

# 最後に確認したニュースのID
last_checked_id = None
# OpenAI APIキーの取得
openai.api_key = os.getenv("OPENAI_API_KEY")

# スキーマを定義
schema = {
    "properties": {
        "category1": {"type": "string"},
        "category2": {"type": "string"},
        "category3": {"type": "string"},
    },
    "required": ["category1"]
}

# OpenAI APIを呼び出す関数
def openai_api_call(model, temperature, messages):
    try:
        response = openai.ChatCompletion.create(
            model=model,
            temperature=temperature,
            messages=messages
        )
        return response.choices[0].message['content']
    except Exception as e:
        print(f"Error in OpenAI API call: {e}")
        traceback.print_exc()
        return None

# カテゴリー作成関数
async def generate_category(content):
    try:
        # LLM (Language Model) を初期化
        llm = ChatOpenAI(temperature=0, model="gpt-3.5-turbo")
        # 抽出チェーンを作成
        chain = create_extraction_chain(schema, llm)
        # チェーンを実行
        extracted_categories = await chain.run(f"あなたは優秀なカテゴリ生成アシスタントです。提供された文章をもとに、カテゴリ(2個から3個)を生成してください。\n\n{content}")
        return extracted_categories
    except Exception as e:
        print(f"Error in category generation: {e}")
        traceback.print_exc()
        return "カテゴリを生成できませんでした"

# リード文作成関数
async def generate_lead(content):
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
async def summarize_content(content):
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
async def generate_opinion(content):
    try:
        opinion = openai_api_call(
        "gpt-4",
        0.6,
        [
            {"role": "system", "content": "あなたは優秀な意見生成アシスタントです。提供された文章をもとに、感想や意見を生成してください。"},
            {"role": "user", "content": content}
        ]
        )
        return opinion
    except Exception as e:
        print(f"Error in opinion generation: {e}")
        traceback.print_exc()
        return "意見を生成できませんでした"

# スプレッドシートへの書き込み関数
def write_to_sheet(summary, opinion, categories, lead):
    creds = None
    # トークンの読み込み
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json')
    service = build('sheets', 'v4', credentials=creds)

    # スプレッドシートIDと範囲を指定
    SPREADSHEET_ID = os.getenv('YOUR_SPREADSHEET_ID')
    RANGE_NAME = 'A1'  # 適切な範囲を指定

    # 現在の時刻を取得
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # データの書き込み
    values = [[now, summary, opinion, ", ".join(categories), lead]]
    body = {'values': values}
    result = service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME,
        valueInputOption='RAW', body=body).execute()
    print(result)

# 新しいHacker Newsのコンテンツを確認する関数
async def check_new_hn_content():
    global last_checked_id
    try:
        # Hacker Newsのトップページをロード
        loader = HNLoader("https://news.ycombinator.com/")
        data = await loader.load()

        # 最新のニュースアイテムのIDを取得
        new_id = data[0]['id']
        max_checked_id = last_checked_id  # 最大の確認済みニュースIDを保持する変数

        # 新しいニュースがあるか確認
        if new_id > last_checked_id:
            # 新しいニュースアイテムを処理
            for item in data:
                # 現在のニュースアイテムのIDを取得
                current_id = item['id']

                # 前回チェックしたID + 1 から最新のニュースIDまで処理
                if last_checked_id < current_id <= new_id:
                    full_content = item['page_content']

                    # 内容を要約
                    summary = await summarize_content(full_content)

                    # 意見を生成
                    opinion = await generate_opinion(summary)

                    # リード文を生成
                    lead = await generate_lead(summary)

                    # カテゴリを生成
                    categories = await generate_category(full_content)

                    # スプレッドシートに要約と意見を書き込む
                    write_to_sheet(summary, opinion, categories, lead)

                    # 最大の確認済みニュースIDを更新
                    max_checked_id = max(max_checked_id, current_id)

            # 最後に確認したニュースのIDを更新
            last_checked_id = max_checked_id

    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
    except openai.Error as e:
        print(f"OpenAI API error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        traceback.print_exc()
