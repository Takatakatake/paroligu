from __future__ import annotations

import streamlit as st

from speech import (
    MAX_TEXT_CHARS,
    RHVoiceError,
    SynthesisOptions,
    find_rhvoice_command,
    prepare_text,
    safe_wav_filename,
    synthesize_wav,
    wav_duration_seconds,
)


SAMPLE_TEXT = "Saluton! Ĉu vi aŭdas la voĉon Spomenka en Esperanto?"


def choose_notation() -> str:
    labels = {
        "unicode": "Unicode",
        "x-system": "x記法",
    }
    options = list(labels)
    if hasattr(st, "segmented_control"):
        selected = st.segmented_control(
            "表記",
            options=options,
            format_func=lambda option: labels[option],
            default="unicode",
        )
        return selected or "unicode"

    return st.radio(
        "表記",
        options=options,
        format_func=lambda option: labels[option],
        horizontal=True,
    )


def render_sidebar() -> SynthesisOptions:
    st.sidebar.header("音声設定")
    rate = st.sidebar.slider("速度", min_value=50, max_value=200, value=100, step=5)
    pitch = st.sidebar.slider("高さ", min_value=50, max_value=200, value=100, step=5)
    volume = st.sidebar.slider("音量", min_value=50, max_value=200, value=100, step=5)
    sample_rate = st.sidebar.selectbox("サンプルレート", options=[24_000, 16_000], index=0)

    command = find_rhvoice_command()
    if command:
        st.sidebar.success("RHVoice: 利用可能")
    else:
        st.sidebar.error("RHVoice: 未検出")

    return SynthesisOptions(
        rate=rate,
        pitch=pitch,
        volume=volume,
        sample_rate=sample_rate,
    )


def main() -> None:
    st.set_page_config(
        page_title="Spomenka Esperanto TTS",
        layout="wide",
    )

    st.title("Spomenka Esperanto TTS")

    options = render_sidebar()

    left, right = st.columns([1.2, 0.8], gap="large")
    with left:
        notation = choose_notation()
        text = st.text_area(
            "エスペラント文",
            value=SAMPLE_TEXT,
            height=260,
            max_chars=MAX_TEXT_CHARS,
        )
        output_name = st.text_input("保存ファイル名", value="spomenka-esperanto.wav")
        synthesize = st.button("音声を生成", type="primary", use_container_width=True)

    with right:
        st.subheader("音声")
        if synthesize:
            for key in ("wav_bytes", "duration"):
                st.session_state.pop(key, None)
            try:
                prepared_text = prepare_text(text, notation)
                wav_bytes = synthesize_wav(prepared_text, options)
            except ValueError as exc:
                st.error(str(exc))
            except RHVoiceError as exc:
                st.error(f"音声生成に失敗しました: {exc}")
            else:
                st.session_state["wav_bytes"] = wav_bytes
                st.session_state["duration"] = wav_duration_seconds(wav_bytes)

        wav_bytes = st.session_state.get("wav_bytes")
        if wav_bytes:
            duration = st.session_state.get("duration", 0.0)
            st.caption(f"{duration:.1f}秒 / {len(wav_bytes) / 1024:.1f} KB")
            st.audio(wav_bytes, format="audio/wav")
            st.download_button(
                "WAVを保存",
                data=wav_bytes,
                file_name=safe_wav_filename(output_name),
                mime="audio/wav",
                use_container_width=True,
            )
        else:
            st.info("まだ音声は生成されていません。")


if __name__ == "__main__":
    main()
