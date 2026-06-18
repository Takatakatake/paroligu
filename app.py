from __future__ import annotations

import streamlit as st

from speech import (
    MAX_TEXT_CHARS,
    RHVoiceError,
    SynthesisOptions,
    SUPPORTED_MP3_BITRATES,
    encode_mp3,
    find_mp3_encoder_command,
    find_rhvoice_command,
    prepare_text,
    safe_mp3_filename,
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


def render_sidebar() -> tuple[SynthesisOptions, int]:
    st.sidebar.header("音声設定")
    rate = st.sidebar.slider("速度", min_value=50, max_value=200, value=100, step=5)
    pitch = st.sidebar.slider("高さ", min_value=50, max_value=200, value=100, step=5)
    volume = st.sidebar.slider("音量", min_value=50, max_value=200, value=100, step=5)
    sample_rate = st.sidebar.selectbox("サンプルレート", options=[24_000, 16_000], index=0)
    mp3_bitrate = st.sidebar.selectbox(
        "MP3ビットレート",
        options=list(SUPPORTED_MP3_BITRATES),
        index=SUPPORTED_MP3_BITRATES.index(128),
        format_func=lambda value: f"{value} kbps",
    )

    command = find_rhvoice_command()
    if command:
        st.sidebar.success("RHVoice: 利用可能")
    else:
        st.sidebar.error("RHVoice: 未検出")

    mp3_command = find_mp3_encoder_command()
    if mp3_command:
        st.sidebar.success("MP3: 利用可能")
    else:
        st.sidebar.warning("MP3: lame 未検出")

    return (
        SynthesisOptions(
            rate=rate,
            pitch=pitch,
            volume=volume,
            sample_rate=sample_rate,
        ),
        mp3_bitrate,
    )


def main() -> None:
    st.set_page_config(
        page_title="Spomenka Esperanto TTS",
        layout="wide",
    )

    st.title("Spomenka Esperanto TTS")

    options, mp3_bitrate = render_sidebar()

    left, right = st.columns([1.2, 0.8], gap="large")
    with left:
        notation = choose_notation()
        text = st.text_area(
            "エスペラント文",
            value=SAMPLE_TEXT,
            height=260,
            max_chars=MAX_TEXT_CHARS,
        )
        output_name = st.text_input("保存ファイル名", value="spomenka-esperanto")
        synthesize = st.button("音声を生成", type="primary", use_container_width=True)

    with right:
        st.subheader("音声")
        if synthesize:
            try:
                prepared_text = prepare_text(text, notation)
                with st.spinner("音声を生成しています..."):
                    wav_bytes = synthesize_wav(prepared_text, options)
                    duration = wav_duration_seconds(wav_bytes)
                    try:
                        mp3_bytes = encode_mp3(wav_bytes, mp3_bitrate)
                    except RHVoiceError as exc:
                        mp3_bytes = None
                        mp3_error = str(exc)
                    else:
                        mp3_error = None
            except ValueError as exc:
                st.error(str(exc))
            except RHVoiceError as exc:
                st.error(f"音声生成に失敗しました: {exc}")
            else:
                st.session_state["wav_bytes"] = wav_bytes
                st.session_state["mp3_bytes"] = mp3_bytes
                st.session_state["mp3_error"] = mp3_error
                st.session_state["duration"] = duration

        wav_bytes = st.session_state.get("wav_bytes")
        if wav_bytes:
            mp3_bytes = st.session_state.get("mp3_bytes")
            mp3_error = st.session_state.get("mp3_error")
            duration = st.session_state.get("duration", 0.0)
            details = [f"{duration:.1f}秒", f"WAV {len(wav_bytes) / 1024:.1f} KB"]
            if mp3_bytes:
                details.append(f"MP3 {len(mp3_bytes) / 1024:.1f} KB")
            st.caption(" / ".join(details))
            st.audio(wav_bytes, format="audio/wav")
            download_columns = st.columns(2)
            with download_columns[0]:
                st.download_button(
                    "WAVを保存",
                    data=wav_bytes,
                    file_name=safe_wav_filename(output_name),
                    mime="audio/wav",
                    use_container_width=True,
                )
            with download_columns[1]:
                if mp3_bytes:
                    st.download_button(
                        "MP3を保存",
                        data=mp3_bytes,
                        file_name=safe_mp3_filename(output_name),
                        mime="audio/mpeg",
                        use_container_width=True,
                    )
                else:
                    st.button("MP3を保存", disabled=True, use_container_width=True)
                    if mp3_error:
                        st.warning(f"MP3変換に失敗しました: {mp3_error}")
        else:
            st.info("まだ音声は生成されていません。")


if __name__ == "__main__":
    main()
