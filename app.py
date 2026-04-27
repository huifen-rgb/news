import os
import re
import json
import streamlit as st
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup

# =========================
# 1. 頁面與樣式
# =========================
st.set_page_config(page_title="智慧化新聞編輯工具", layout="centered")

st.markdown("""
<style>
    .teleprompter { 
        background-color: #1a1a1a; 
        color: #00ff00; 
        padding: 25px; 
        border-radius: 12px; 
        line-height: 1.8; 
        font-size: 26px; 
        border-left: 10px solid #ff4b4b; 
        margin-top: 10px; 
        white-space: pre-wrap; 
        font-family: 'Microsoft JhengHei', sans-serif;
    }
    .headline-box {
        background: #fff3cd; 
        color: #111; 
        padding: 18px;
        border-radius: 10px; 
        font-size: 26px; 
        font-weight: bold;
        border-left: 8px solid #ff9800; 
        margin-bottom: 15px;
        line-height: 1.5;
    }
    .focus-box {
        background: #e8f4ff; 
        color: #111; 
        padding: 16px;
        border-radius: 10px; 
        font-size: 18px; 
        line-height: 1.7;
        border-left: 8px solid #2196f3; 
        margin-bottom: 15px;
        white-space: pre-wrap;
    }
    .meta-box {
        background: #f5f5f5;
        color: #333;
        padding: 12px 16px;
        border-radius: 8px;
        font-size: 15px;
        line-height: 1.6;
        margin-bottom: 15px;
    }
</style>
""", unsafe_allow_html=True)

# =========================
# 2. 側邊欄設定 (secrets.toml 智慧化兼容版)
# =========================
with st.sidebar:
    st.title("⚙️ 智慧化設定")

    # 定義一個變數來存 API Key
    api_key = None

    try:
        # 1. 優先嘗試從 Streamlit 的 secrets 保險箱拿資料
        # 在 Render 上，只要妳設定了 Environment Variables，
        # Streamlit 其實會自動把它映射到 st.secrets 裡！
        if "GEMINI_API_KEY" in st.secrets:
            api_key = st.secrets["GEMINI_API_KEY"]
        
        # 2. 如果保險箱沒東西，才找系統環境變數 (Render 的標準做法)
        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY")

    except Exception:
        # 如果連 st.secrets 這個功能都沒載入 (某些環境會報錯)，就改用 os
        api_key = os.getenv("GEMINI_API_KEY")

    # --- 最後備案：如果都沒抓到，才讓使用者手動輸入 ---
    if not api_key:
        api_key = st.text_input(
            "輸入 Gemini API Key",
            type="password",
            placeholder="尚未偵測到密鑰，請手動輸入"
        )

    if api_key:
        st.success("✅ 智慧化金鑰已就緒")
    else:
        st.warning("⚠️ 待命：請提供 API Key")

# =========================
# 3. 主介面
# =========================
st.title("📺 專業編輯室：講稿智慧化整併")

tab1, tab2 = st.tabs(["🔗 網址自動抓取", "✍️ 手動貼上內文"])

with tab1:
    u1 = st.text_input("新聞來源網址 1", key="u1_path")
    u2 = st.text_input("新聞來源網址 2", key="u2_path")
    u3 = st.text_input("新聞來源網址 3", key="u3_path")

with tab2:
    manual_text = st.text_area(
        "若自動抓取失敗，請直接貼上文字：",
        height=250,
        placeholder="在此輸入新聞稿或資料..."
    )

editor_focus = st.text_area(
    "📌 提示重點｜人工提醒 AI 必須寫進去的重點",
    height=120,
    placeholder="例如：要強調民眾影響、金額變化、時間點、官方說法、爭議點..."
)

submitted = st.button("🚀 生成標題＋30s 講稿")

# =========================
# 4. 網址抓取
# =========================
def fetch_content(url):
    if not url or not url.startswith("http"):
        return None

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        }

        res = requests.get(url.strip(), timeout=10, headers=headers)
        res.encoding = res.apparent_encoding

        if res.status_code != 200:
            return None

        soup = BeautifulSoup(res.text, "html.parser")

        for s in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            s.decompose()

        article = (
            soup.find("article")
            or soup.find("main")
            or soup.find(class_="article-content")
            or soup.find(class_="story")
            or soup.find(class_="content")
            or soup.find(class_="news-content")
            or soup.find(class_="article_body")
        )

        text = article.get_text(separator=" ", strip=True) if article else soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()

        return text[:3000]

    except Exception:
        return None

# =========================
# 5. 風格設定
# =========================
VALID_STYLES = ["穩重資訊型", "強烈衝突型", "口語吸睛型"]

def get_title_style_prompt(style):
    styles = {
        "穩重資訊型": """
- 標題要資訊清楚、重點直接
- 用字穩重精準
- 避免過度情緒化
- 適合政策、財經、國際、官方資訊、制度變動、數據型新聞
""",
        "強烈衝突型": """
- 標題節奏要快、有事件張力
- 可強化衝突、轉折、關鍵動詞
- 適合政治攻防、社會爭議、突發事件、對立情境、危機事件
- 但不可誇大或失真
""",
        "口語吸睛型": """
- 標題要口語、吸睛、貼近生活
- 強調民眾感受與實際影響
- 適合民生消費、娛樂、社群話題、生活提醒
- 可帶一點生活新聞感
"""
    }
    return styles.get(style, styles["穩重資訊型"])

def get_anchor_tone(style):
    tones = {
        "穩重資訊型": """
- 口播語氣冷靜、專業、節奏穩
- 用字精準，不過度口語
- 避免情緒性形容
""",
        "強烈衝突型": """
- 口播語氣節奏快、強烈、有張力
- 可使用強動詞與對比
- 情緒可略帶張力，但不得誇張
""",
        "口語吸睛型": """
- 口播語氣較口語、貼近觀眾
- 強調生活感、影響感與民眾視角
- 句子要好懂、順口
"""
    }
    return tones.get(style, tones["穩重資訊型"])

def get_style_instruction(selected_style):
    if selected_style == "AI自動判斷":
        return """
【風格判斷】
請先根據新聞內容與編輯提示，自行判斷最適合的標題與主播語氣風格。

只能從以下三種選一種：
1. 穩重資訊型：政策、財經、國際、官方資訊、制度變動、數據型新聞
2. 強烈衝突型：政治攻防、社會爭議、突發事件、衝突、指控、危機、對立情境
3. 口語吸睛型：民生消費、生活提醒、娛樂、社群話題、民眾感受

判斷後，JSON 的 selected_style 欄位必須只填入：
穩重資訊型、強烈衝突型、口語吸睛型 其中之一。

標題與講稿都必須符合你判斷出的 selected_style。
"""
    else:
        return f"""
【風格指定】
本次指定風格為：{selected_style}

【標題風格】
{get_title_style_prompt(selected_style)}

【主播語氣風格】
{get_anchor_tone(selected_style)}

JSON 的 selected_style 欄位請填入：{selected_style}
"""

# =========================
# 6. Gemini 備援模型
# =========================
def generate_with_fallback(prompt, mode="穩定優先"):
    if mode == "速度優先":
        model_names = [
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash"
        ]
    else:
        model_names = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite"
        ]

    last_error = None

    for model_name in model_names:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)

            if response and getattr(response, "text", None):
                return response.text, model_name

        except Exception as e:
            last_error = e
            continue

    raise Exception(f"所有備援模型都失敗。最後錯誤：{last_error}")

# =========================
# 7. 清理與標題工具
# =========================
def extract_json(text):
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, re.S)
    if match:
        return json.loads(match.group())

    raise ValueError("模型回傳格式不是有效 JSON")

def clean_script_text(text):
    text = str(text).strip()
    text = text.replace("\n", "")
    text = re.sub(r"\s+", "", text)

    text = text.replace("＝＝＝TAKE＝＝＝", "===TAKE===")
    text = text.replace("=== TAKE ===", "===TAKE===")
    text = text.replace("===TAKE ===", "===TAKE===")
    text = text.replace("=== TAKE===", "===TAKE===")
    text = text.replace("＝TAKE＝", "===TAKE===")

    return text

def count_title_chars(title):
    return len(str(title).replace(" ", ""))

def remove_title_punctuation(title):
    title = str(title).strip()
    title = re.sub(r"\s+", "", title)
    title = re.sub(r"[，。！？、：「」『』（）()《》【】\[\]！?.,:;；\-—_]", "", title)
    return title

def fix_title_length(title):
    title = remove_title_punctuation(title)

    # 不硬切 23，避免「嫌犯已遭」這種斷尾
    # 先保留到 28，後面讓 refine 決定是否重寫
    if len(title) > 28:
        title = title[:28]

    return title

def smart_break_title(title):
    title = str(title).strip().replace(" ", "")

    if len(title) < 12:
        return title

    # 三段式邏輯的「事件切點」：主詞/場景 + 事件 + 結果
    event_keywords = [
        "驚傳", "傳出", "傳槍響", "爆發", "發生", "曝光",
        "宣布", "通過", "拍板", "上路", "啟動", "證實",
        "開罰", "調漲", "下修", "擴大", "新增", "取消",
        "撤離", "落網", "逮捕", "送醫", "示警", "影響"
    ]

    result_keywords = [
        "川普", "嫌犯", "警方", "白宮", "民眾", "政府", "總統",
        "平安", "緊急", "撤離", "落網", "送醫", "開罰", "上路"
    ]

    # 優先找結果段開頭，讓標題像：事件主句 結果主句
    for keyword in result_keywords:
        idx = title.find(keyword)
        if 7 <= idx <= len(title) - 5:
            return title[:idx] + " " + title[idx:]

    # 再找事件動詞後切
    for keyword in event_keywords:
        if keyword in title:
            idx = title.index(keyword) + len(keyword)
            if 7 <= idx <= len(title) - 5:
                return title[:idx] + " " + title[idx:]

    # fallback：中間切
    mid = len(title) // 2
    if mid < 7:
        mid = 7
    if mid > len(title) - 5:
        mid = len(title) - 5

    return title[:mid] + " " + title[mid:]

def is_incomplete_title(title):
    title_no_space = str(title).replace(" ", "")

    bad_endings = [
        "遭", "被", "已", "將", "仍", "恐", "傳", "稱", "指",
        "嫌犯", "警方", "總統", "白宮", "緊急", "護送", "離場",
        "已遭", "遭緊急", "遭護送", "傳槍響", "驚傳"
    ]

    return any(title_no_space.endswith(ending) for ending in bad_endings)

def normalize_title(title):
    title = fix_title_length(title)
    title = smart_break_title(title)

    # 保證只有一個半形空格
    title = re.sub(r"\s+", " ", title).strip()
    parts = title.split(" ")

    if len(parts) > 2:
        title = parts[0] + " " + "".join(parts[1:])

    return title

def refine_title_if_needed(title, source_text, editor_focus, selected_style, model_choice):
    title_len = count_title_chars(title)

    if (
        20 <= title_len <= 23
        and " " in title
        and "，" not in title
        and not is_incomplete_title(title)
    ):
        return title

    refine_prompt = f"""
你是一位台灣電視新聞標題編輯。請只輸出一行新聞標題，不要 JSON，不要說明。

【目前標題】
{title}

【新聞資料】
{source_text[:1200]}

【編輯提示】
{editor_focus}

【風格】
{selected_style}

【重寫要求】
- 標題必須是 20 到 23 個中文字，不含半形空格計算
- 必須使用一個半形空格自然斷句
- 不要使用逗號
- 不要使用任何標點符號
- 標題語意必須完整
- 標題需具備三段式新聞邏輯：主詞或場景、核心事件、結果或影響
- 但輸出只能放一個半形空格，不要放兩個空格
- 不能結尾停在「遭」「已遭」「將」「恐」「嫌犯」「警方」「緊急」「護送」等未完成詞
- 若超過字數，請改寫濃縮，不要直接截斷
- 要像台灣電視新聞標題
- 要保留新聞核心事實
- 範例格式：白宮晚宴驚傳槍響 川普撤離嫌犯落網
"""

    try:
        refined_text, _ = generate_with_fallback(refine_prompt, model_choice)
        refined_title = refined_text.strip().split("\n")[0]
        return normalize_title(refined_title)
    except Exception:
        return normalize_title(title)

# =========================
# 8. 核心生成
# =========================
if submitted:
    if not api_key:
        st.error("❌ 請先提供 Gemini API Key。")

    else:
        genai.configure(api_key=api_key)

        target_urls = [u1, u2, u3]
        combined_text = manual_text.strip() if manual_text and manual_text.strip() else ""
        fetched_count = 0

        if not combined_text:
            with st.spinner("🔍 正在智慧化抓取內容..."):
                for u in target_urls:
                    if u:
                        content = fetch_content(u)
                        if content:
                            fetched_count += 1
                            combined_text += f"\n\n{content}"

        if len(combined_text.strip()) < 20:
            st.warning("❌ 內容不足，請確認網址或手動貼上。")

        else:
            with st.spinner("🤖 正在生成標題與倒三角講稿..."):
                prompt = f"""
你是一位台灣電視新聞主編。請根據新聞資料與編輯提示，產出新聞標題與 30-40 秒播報稿。

請務必只輸出 JSON，不要加入任何說明文字。

JSON 格式如下：
{{
  "selected_style": "穩重資訊型 或 強烈衝突型 或 口語吸睛型",
  "title": "20到23個中文字並含一個半形空格的新聞標題",
  "script": "核心事實第一句===TAKE===次要資訊細節"
}}

【編輯提示重點】
以下是編輯人工提醒你必須注意、優先寫入或避免遺漏的重點：
{editor_focus}

{get_style_instruction(title_style)}

【標題要求】
- 必須是 20 到 23 個中文字，半形空格不計入字數
- 必須使用一個半形空格自然斷句
- 不要使用逗號
- 不含任何標點符號
- 絕對不能超過 23 個中文字
- 不要少於 20 個中文字
- 標題語意必須完整，不能被截斷
- 標題需具備三段式新聞邏輯：主詞或場景、核心事件、結果或影響
- 但輸出只能放一個半形空格，不要放兩個空格
- 要像台灣電視新聞標題
- 要抓出最有新聞價值的重點
- 若編輯提示重點有指定方向，標題要優先呼應

【講稿要求】
- 30 到 40 秒
- 約 140 到 180 字
- 第一句必須是最核心事實
- 第一句後緊接 ===TAKE===
- ===TAKE=== 前後嚴禁空格、換行或標點符號
- 必須符合 selected_style 的主播語氣
- 使用台灣電視新聞口播節奏
- 不要加入標題
- 不要條列
- 必須優先納入編輯提示重點

資料來源：
{combined_text}
"""

                try:
                    result_text, used_model = generate_with_fallback(prompt, model_choice)
                    data = extract_json(result_text)

                    selected_style = str(data.get("selected_style", "")).strip()

                    if selected_style not in VALID_STYLES:
                        selected_style = title_style if title_style in VALID_STYLES else "穩重資訊型"

                    raw_title = data.get("title", "").strip()
                    title = normalize_title(raw_title)
                    title = refine_title_if_needed(
                        title=title,
                        source_text=combined_text,
                        editor_focus=editor_focus,
                        selected_style=selected_style,
                        model_choice=model_choice
                    )

                    script = clean_script_text(data.get("script", ""))

                    st.success(f"✅ 生成完成！使用模型：{used_model}")

                    st.subheader("📰 20-23字新聞標題")
                    st.markdown(
                        f'<div class="headline-box">{title}</div>',
                        unsafe_allow_html=True
                    )

                    st.markdown(
                        f"""
                        <div class="meta-box">
                        標題字數：{count_title_chars(title)} 字｜風格：{selected_style}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                    st.subheader("📌 人工提示重點")
                    st.markdown(
                        f'<div class="focus-box">{editor_focus if editor_focus else "未填寫人工提示重點"}</div>',
                        unsafe_allow_html=True
                    )

                    st.subheader("🎤 專業播報稿 30-40s")
                    st.markdown(
                        f'<div class="teleprompter">{script}</div>',
                        unsafe_allow_html=True
                    )

                    st.write("---")

                    full_output = (
                        f"【標題】\n{title}\n\n"
                        f"【風格】\n{selected_style}\n\n"
                        f"【人工提示重點】\n{editor_focus}\n\n"
                        f"【播報稿】\n{script}"
                    )

                    try:
                        st.copy_to_clipboard(
                            full_output,
                            before_copy_label="📋 一鍵複製全部內容",
                            after_copy_label="✅ 複製成功！"
                        )
                    except Exception:
                        st.text_area("📋 複製用文字", full_output, height=220)

                    st.caption(f"講稿字數：{len(script)} 字")

                except Exception as e:
                    st.error(f"生成失敗：{str(e)}")
