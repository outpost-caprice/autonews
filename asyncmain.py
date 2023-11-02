import os
import requests
import traceback
from langchain.document_loaders import HNLoader
from langchain.chat_models import ChatOpenAI
from langchain.chains import create_extraction_chain
import openai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import datetime
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

async def async_check_new_content():
  global last_checked_id
  loader = HNLoader("https://news.ycombinator.com/")
  data = loader.load()
  
  new_id = data[0]['id']
  return new_id, last_checked_id

async def async_fetch_news_content(new_id, last_checked_id): 
    if new_id != last_checked_id:
        full_content = new_id['page_content']  
        return [full_content] 

async def async_summarize_content(content):
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


async def async_generate_category(content):
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

async def async_generate_opinion(summary):
    try:
        opinion = openai_api_call(
        "gpt-4",
        0.6,
        [
            {"role": "system", "content": "あなたは優秀な意見生成アシスタントです。提供された文章をもとに、感想や意見を生成してください。"},
            {"role": "user", "content": summary}
        ]
        )
        return opinion
    except Exception as e:
        print(f"Error in opinion generation: {e}")
        traceback.print_exc()
        return "意見を生成できませんでした"

async def async_generate_lead(summary):
    try:
        lead = openai_api_call(
        "gpt-3.5-turbo-0613",
        0.6,
        [
            {"role": "system", "content": "あなたは優秀なリード文生成アシスタントです。提供された文章をもとに、日本語のリード文を生成してください。"},
            {"role": "user", "content": summary}
        ]
    )
        return lead
    except Exception as e:
        print(f"Error in lead generation: {e}")
        traceback.print_exc()
        return "リード文を生成できませんでした"

def write_to_sheet(summary, opinion, categories, lead):
    # スプレッドシートへの書き込み関数
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
    print ("書き込みが完了しました")

async def process_new_content():
    new_id, last_checked_id_temp = await async_check_new_content()
    if new_id != last_checked_id:
        full_content_list = await async_fetch_news_content(new_id, last_checked_id)

        # summaries and categories processing
        summaries = []
        categories = []
        for content in full_content_list:
            # using asyncio.create_task to create a new task and await on it immediately
            summary_task = asyncio.create_task(async_summarize_content(content))
            category_task = asyncio.create_task(async_generate_category(content))
            
            # awaiting on individual tasks to handle timeout and errors separately
            try:
                summary = await asyncio.wait_for(summary_task, timeout=10)  # 10 seconds timeout
                summaries.append(summary)
            except asyncio.TimeoutError:
                print("Summarization task timed out")
                summaries.append(None)  # append None or an empty string if task fails or times out
            except Exception as e:
                print(f"Error in summarization: {e}")
                summaries.append(None)
                
            try:
                category = await asyncio.wait_for(category_task, timeout=10)  # 10 seconds timeout
                categories.append(category)
            except asyncio.TimeoutError:
                print("Category generation task timed out")
                categories.append(None)  # append None or an empty string if task fails or times out
            except Exception as e:
                print(f"Error in category generation: {e}")
                categories.append(None)
        # opinions and leads processing
        opinions = []
        leads = []
        for summary in summaries:
            if summary:  # check if summary is not None or empty before proceeding
                opinion_task = asyncio.create_task(async_generate_opinion(summary))
                lead_task = asyncio.create_task(async_generate_lead(summary))
                
                # awaiting on individual tasks to handle timeout and errors separately
                try:
                    opinion = await asyncio.wait_for(opinion_task, timeout=10)  # 10 seconds timeout
                    opinions.append(opinion)
                except asyncio.TimeoutError:
                    print("Opinion generation task timed out")
                    opinions.append(None)  # append None or an empty string if task fails or times out
                except Exception as e:
                    print(f"Error in opinion generation: {e}")
                    opinions.append(None)
                    
                try:
                    lead = await asyncio.wait_for(lead_task, timeout=10)  # 10 seconds timeout
                    leads.append(lead)
                except asyncio.TimeoutError:
                    print("Lead generation task timed out")
                    leads.append(None)  # append None or an empty string if task fails or times out
                except Exception as e:
                    print(f"Error in lead generation: {e}")
                    leads.append(None)
        # writing to spreadsheet
        for i in range(len(summaries)):
            if summaries[i]:  # check if summary is not None or empty before proceeding
                # If any of the values are None or empty, replace them with a default message
                summary = summaries[i]
                category = categories[i] if categories[i] else "カテゴリを生成できませんでした"
                opinion = opinions[i] if opinions[i] else "意見を生成できませんでした"
                lead = leads[i] if leads[i] else "リード文を生成できませんでした"
                write_to_sheet(summary, opinion, category, lead)
        last_checked_id = new_id

# 非同期関数の実行
if __name__ == "__main__":
  asyncio.run(process_new_content())