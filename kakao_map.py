import os

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


SDK_LOADER_JS = r"""
window.chachachaKakao = window.chachachaKakao || function (appkey, libraries) {
  if (window.chachachaKakaoSdk) return window.chachachaKakaoSdk;
  const pending = new Promise((resolve, reject) => {
    // 페이지마다 필요한 라이브러리가 달라도 SDK는 문서당 한 번만 불러온다.
    const names = new Set(['clusterer', ...String(libraries || '').split(',').filter(Boolean)]);
    const script = document.createElement('script');
    const fail = () => {
      clearTimeout(timer);
      script.remove();
      if (window.chachachaKakaoSdk === pending) window.chachachaKakaoSdk = null;
      reject(new Error('kakao sdk unavailable'));
    };
    const timer = setTimeout(fail, 8000);
    script.src = 'https://dapi.kakao.com/v2/maps/sdk.js?appkey=' + encodeURIComponent(appkey)
      + '&autoload=false&libraries=' + [...names].join(',');
    script.onerror = fail;
    script.onload = () => {
      if (!window.kakao || !window.kakao.maps || !window.kakao.maps.load) { fail(); return; }
      window.kakao.maps.load(() => { clearTimeout(timer); resolve(window.kakao); });
    };
    document.head.appendChild(script);
  });
  window.chachachaKakaoSdk = pending;
  return pending;
};
"""


def _secret(name: str, environment: str) -> str:
    try:
        section = st.secrets.get("kakao", {})
        value = section.get(name) if hasattr(section, "get") else None
    except (KeyError, FileNotFoundError, StreamlitSecretNotFoundError):
        value = None
    if not isinstance(value, str) or not value.strip():
        value = os.environ.get(environment, "")
    return value.strip()


def javascript_key() -> str:
    return _secret("javascript_api_key", "KAKAO_JAVASCRIPT_API_KEY")


def rest_key() -> str:
    return _secret("rest_api_key", "KAKAO_REST_API_KEY")
