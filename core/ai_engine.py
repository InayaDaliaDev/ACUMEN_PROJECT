"""Shared Gemini engine. No Streamlit dependency."""
from core.utils import extract_text

DEFAULT_FALLBACK_MODELS=['gemini-2.5-flash','gemini-2.5-flash-lite','gemini-flash-latest']

def build_fallback_chain(primary):
    out=[]
    for m in [primary,*DEFAULT_FALLBACK_MODELS]:
        if m and m not in out: out.append(m)
    return out

def classify_error(e):
    t=str(e).lower(); n=e.__class__.__name__.lower()
    if 'permission' in n or 'unauth' in t or 'api key' in t: return 'auth','The AI engine rejected the API key. Check Settings.'
    if 'quota' in t or '429' in t or 'resource' in n: return 'quota',"Gemini's quota is temporarily exhausted. Try again later."
    if 'timeout' in n or 'timed out' in t: return 'timeout','The AI engine took too long to respond. Try again.'
    return 'unknown','The AI engine is temporarily unavailable. Your data is still safe.'

def invoke_llm_with_fallback(system_prompt, history, api_key, model='gemini-2.5-flash', temperature=.55, timeout=60):
    if not api_key: raise ValueError('Missing Gemini API key')
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
    messages=[SystemMessage(content=system_prompt)]
    for m in history or []:
        role=m.get('role','user'); content=m.get('content','')
        messages.append(AIMessage(content=content) if role=='assistant' else HumanMessage(content=content))
    last=None
    for name in build_fallback_chain(model):
        try:
            llm=ChatGoogleGenerativeAI(model=name,google_api_key=api_key,temperature=temperature,timeout=timeout,max_retries=1)
            return llm.invoke(messages)
        except Exception as e: last=e
    raise last or RuntimeError('All model attempts failed')

def generate_text(system_prompt,user_prompt,api_key,model='gemini-2.5-flash',temperature=.55,timeout=60):
    r=invoke_llm_with_fallback(system_prompt,[{'role':'user','content':user_prompt}],api_key,model,temperature,timeout)
    return extract_text(r.content)
