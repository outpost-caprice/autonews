import os
import requests
import traceback
from langchain.document_loaders import HNLoader
from langchain.chat_models import ChatOpenAI
from langchain.chains import create_extraction_chain
import openai
from google.oauth2.credentials import Credentials
from googleapiclient import discovery

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
def generate_category(content):
    try:
        # LLM (Language Model) を初期化
        llm = ChatOpenAI(temperature=0.6, model="gpt-3.5-turbo")
        # 抽出チェーンを作成
        chain = create_extraction_chain(schema, llm)
        # チェーンを実行
        extracted_categories = chain.run(f"あなたは優秀なカテゴリ生成アシスタントです。提供された文章をもとに、カテゴリ(2個から3個)を生成してください。\n\n{content}")
        return extracted_categories
    except Exception as e:
        print(f"Error in category generation: {e}")
        traceback.print_exc()
        return "カテゴリを生成できませんでした"


def generate_lead(content):
    try:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo-0613",
            temperature=0.6,
            messages=[
                {"role": "system", "content": "あなたは優秀なリード文生成アシスタントです。提供された文章をもとに、日本語のリード文を生成してください。"},
                {"role": "user", "content": content}
            ]
        )
        lead = response.choices[0].text.strip()
        return lead
    except Exception as e:
        print(f"Error in lead generation: {e}")
        traceback.print_exc()
        return "リード文を生成できませんでした"
    




# 要約用の関数
def summarize_content(content):
    try:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo-16k-0613",
            temperature=0,
            messages=[
                {"role": "system", "content": "あなたは優秀な要約アシスタントです。提供された文章をもとに、できる限り正確な内容にすることを意識して要約してください。"},
                {"role": "user", "content": content}
            ]
        )
        return completion.choices[0].message['content']
    except Exception as e:
        print(f"Error in summarization: {e}")
        traceback.print_exc()
        return "要約できませんでした"

# 意見生成用の関数
def generate_opinion(content):
    try:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        completion = openai.ChatCompletion.create(
            model="gpt-4",
            temperature=0.6,
            messages=[
                {"role": "system", "content": "あなたは優秀な意見生成アシスタントです。提供された文章をもとに、感想や意見を生成してください。"},
                {"role": "user", "content": content}
            ]
        )
        return completion.choices[0].message['content']
    except Exception as e:
        print(f"Error in opinion generation: {e}")
        traceback.print_exc()
        return "意見を生成できませんでした"

def write_to_sheet(summary, opinion):
    creds = None
    # トークンの読み込み
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json')
    service = build('sheets', 'v4', credentials=creds)

    # スプレッドシートIDと範囲を指定
    SPREADSHEET_ID = 'YOUR_SPREADSHEET_ID'
    RANGE_NAME = 'A1'  # 適切な範囲を指定

    # データの書き込み
    values = [[summary, opinion]]
    body = {'values': values}
    result = service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME,
        valueInputOption='RAW', body=body).execute()

# 新しいHacker Newsのコンテンツを確認する関数
def check_new_hn_content(request):
    global last_checked_id
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

            # IFTTTのWebhook URL
            webhook_url = os.getenv("IFTTT_WEBHOOK_URL")

            # IFTTTに送信するデータ
            data = {"value1": f"新しいニュースがあります(ID: {new_id})", "value2": summary, "value3": opinion}

            # IFTTTのWebhookを通じてSlackに投稿
            requests.post(webhook_url, json=data)

            # スプレッドシートに要約と意見を書き込む
            write_to_sheet(summary, opinion)

            # 最後に確認したニュースのIDを更新
            last_checked_id = new_id
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
    except openai.Error as e:
        print(f"OpenAI API error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        traceback.print_exc()

#"C:\Users\araki\AppData\Local\Programs\Python\Python310\python.exe"