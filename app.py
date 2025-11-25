import os
import time
import streamlit as st
from openai import OpenAI

# --------- BASIC CONFIG ---------
st.set_page_config(
    page_title="Penguin Love Judge",
    page_icon="🐧",
    layout="wide"
)

# --------- SESSION STATE ---------
if "view" not in st.session_state:
    st.session_state.view = "input"      # "input" or "verdict"
if "verdict_md" not in st.session_state:
    st.session_state.verdict_md = ""     # model output
if "verdict_revealed" not in st.session_state:
    st.session_state.verdict_revealed = False

# --------- OPENAI CLIENT ---------
api_key = os.getenv("OPENAI_API_KEY") or st.secrets["OPENAI_API_KEY"]
client = OpenAI(api_key=api_key)

# --------- PAGE HEADER (common) ---------
st.title("🐧 Penguin Love Judge")
st.caption("A soft but honest third-party view for couples. Not therapy, just a cute mediator.")
st.markdown("---")


# ===================== HELPER FUNCTIONS =====================

def extract_section(text: str, start_marker: str, end_markers: list[str]) -> str:
    """Extract the section of text between start_marker and the next of end_markers."""
    if start_marker not in text:
        return ""
    start = text.index(start_marker) + len(start_marker)
    ends = []
    for m in end_markers:
        pos = text.find(m, start)
        if pos != -1:
            ends.append(pos)
    end = min(ends) if ends else len(text)
    return text[start:end].strip()


def split_overall_and_reason(responsibility_section: str):
    """Split out the 'Overall split: ...' line and keep the rest as reasoning text."""
    if not responsibility_section:
        return "", responsibility_section

    lines = responsibility_section.splitlines()
    overall_line = ""
    remaining_lines = []
    for line in lines:
        if "Overall split" in line and not overall_line:
            overall_line = line.lstrip("-").strip()
        else:
            remaining_lines.append(line)
    remaining_text = "\n".join(remaining_lines).strip()
    return overall_line, remaining_text


def split_by_partner_markers(text: str, marker_a: str, marker_b: str):
    """
    Split a section into content for Partner A and Partner B based on markers like:
    'For Partner A:' / 'For Partner B:'
    """
    if not text:
        return "", ""

    lower = text.lower()
    idx_a = lower.find(marker_a.lower())
    idx_b = lower.find(marker_b.lower()) if marker_b else -1

    part_a = ""
    part_b = ""

    if idx_a != -1:
        if idx_b != -1 and idx_b > idx_a:
            part_a = text[idx_a:idx_b].strip()
            part_b = text[idx_b:].strip()
        else:
            part_a = text[idx_a:].strip()
    else:
        part_a = text.strip()

    return part_a, part_b


def clean_empty_bullets(text: str) -> str:
    """Remove lines that are just '-' or '*' so we don't get empty bullets."""
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if s in ("-", "*", "•", ""):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def section_to_html(text: str) -> str:
    """
    Very simple Markdown → HTML for our use:
    - Lines starting with "- " become <li>
    - Everything else becomes <p>
    """
    if not text:
        return ""
    lines = text.splitlines()
    blocks = []
    current_ul = []

    def flush_ul():
        nonlocal current_ul
        if current_ul:
            lis = "".join(f"<li>{item}</li>" for item in current_ul)
            blocks.append(f"<ul>{lis}</ul>")
            current_ul = []

    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("- "):
            current_ul.append(s[2:])
        else:
            flush_ul()
            blocks.append(f"<p>{s}</p>")
    flush_ul()
    return "".join(blocks)


# ===================== VIEW 1: INPUT PAGE =====================
if st.session_state.view == "input":

    # --------- RELATIONSHIP CONTEXT ---------
    st.subheader("Relationship Context")

    col_ctx1, col_ctx2, col_ctx3 = st.columns(3)

    with col_ctx1:
        relationship_stage = st.selectbox(
            "Relationship stage",
            ["Just talking", "Dating", "Serious relationship", "Engaged/Married", "Complicated"],
            index=1,
            key="relationship_stage"
        )

    with col_ctx2:
        conflict_severity = st.selectbox(
            "How serious is this conflict?",
            ["Small misunderstanding", "Medium", "Big fight"],
            index=0,
            key="conflict_severity"
        )

    with col_ctx3:
        tone_pref = st.selectbox(
            "Penguin's verdict tone",
            ["Very gentle", "Balanced", "Direct but kind"],
            index=1,
            key="tone_pref"
        )

    st.markdown("---")

    # --------- PARTNER INPUTS ---------
    st.subheader("Tell the Penguin what happened")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("### Partner A")
        name_a = st.text_input("Name / nickname (optional)", key="name_a")
        mood_a = st.selectbox(
            "Current mood",
            ["😡 Angry", "😢 Sad", "😞 Disappointed", "😐 Confused", "🙂 Okay"],
            key="mood_a"
        )
        event_a = st.text_area("What happened? (your perspective)", height=150, key="event_a")
        reason_a = st.text_area("Why are you upset?", height=150, key="reason_a")

    with col_b:
        st.markdown("### Partner B")
        name_b = st.text_input("Name / nickname (optional)", key="name_b")
        mood_b = st.selectbox(
            "Current mood ",
            ["😡 Angry", "😢 Sad", "😞 Disappointed", "😐 Confused", "🙂 Okay"],
            key="mood_b"
        )
        event_b = st.text_area("What happened? (your perspective)", height=150, key="event_b")
        reason_b = st.text_area("Why are you upset?", height=150, key="reason_b")

    st.markdown("---")

    # --------- BUILD PROMPT ---------
    def build_user_prompt() -> str:
        label_a = name_a.strip() if name_a.strip() else "Partner A"
        label_b = name_b.strip() if name_b.strip() else "Partner B"

        return f"""
The following information comes from a couple asking you for relationship mediation.

Relationship context:
- Relationship stage: {relationship_stage}
- Conflict severity: {conflict_severity}
- Preferred tone: {tone_pref}

{label_a}:
- Mood: {mood_a}
- What happened (their perspective): {event_a}
- Why they are upset: {reason_a}

{label_b}:
- Mood: {mood_b}
- What happened (their perspective): {event_b}
- Why they are upset: {reason_b}
"""

    # ------- Stronger, therapist-like system prompt -------
    system_prompt = """
You are "Penguin Love Judge", a neutral, emotionally intelligent relationship mediator.
Your style combines:
- The fairness of a wise judge, and
- The warmth and practicality of a couples therapist.

General rules:
- You NEVER shame, blame, or mock either partner.
- You always assume that both partners are trying their best with the skills they currently have.
- You validate emotions, but you are honest about unhelpful behaviours on BOTH sides.
- You focus on specific, observable behaviours and communication patterns, not on personality attacks.
- Be culturally sensitive and avoid assumptions about gender roles.

Your goals in every case:
1. Help both partners feel understood.
2. Clarify how each of them contributed to the current dynamic.
3. Offer concrete, realistic next steps they can actually do this week.
4. Encourage more curiosity, listening, and collaboration between them.

Output structure (very important — follow EXACTLY):

## 📝 Case summary
1–3 short sentences. Neutral, no blaming, no taking sides.

## 💗 Partner A – feelings & needs
- 2–4 bullet points about emotions
- 2–4 bullet points about deeper needs / values (e.g., respect, safety, clarity, affection)

## 💗 Partner B – feelings & needs
- 2–4 bullet points about emotions
- 2–4 bullet points about deeper needs / values

## ⚖️ Responsibility split
- Overall split: Partner A XX% / Partner B YY%
- Why this split makes sense:
  - 2–4 bullet points explaining specific behaviours or patterns (not personality)

## 🔧 How both of you can improve
For Partner A:
- 2–4 bullet points, each is a clear, behavioural suggestion
- Focus on what they can DO or SAY differently (e.g., "pause before replying", "ask clarifying questions", "share feelings without blame")

For Partner B:
- 2–4 bullet points, same style: clear, behavioural, doable

## 💬 Example sentences you could say to each other
For Partner A to say:
- 2–4 "I" statements that A could say to B. They should be:
  - Kind but honest
  - Focused on feelings and needs, not accusations

For Partner B to say:
- 2–4 "I" statements that B could say to A, same style.

Rules for formatting:
- DO NOT create empty bullet points.
- DO NOT write placeholder lines like "-" with no text.
- Use clear, simple language that non-native English speakers can understand.
- Keep the tone warm, firm, and hopeful.

End with ONE short sentence reminding them that this is friendly guidance, not professional therapy.
"""

    # --------- BUTTON: GO TO VERDICT VIEW ---------
    if st.button("Ask the Penguin Judge 🐧⚖️"):
        if not event_a.strip() or not event_b.strip() or not reason_a.strip() or not reason_b.strip():
            st.warning("Please fill in all fields for both partners before asking the Penguin Judge.")
        else:
            with st.spinner("The Penguin Judge is thinking and raising the gavel... 🐧🔨"):
                user_prompt = build_user_prompt()

                completion = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.6,
                )

                st.session_state.verdict_md = completion.choices[0].message.content
                st.session_state.view = "verdict"
                st.session_state.verdict_revealed = False  # reset

            st.rerun()

# ===================== VIEW 2: VERDICT PAGE =====================
else:
    # Get labels from previous page
    raw_a = st.session_state.get("name_a", "") or ""
    raw_b = st.session_state.get("name_b", "") or ""
    label_a = raw_a.strip() or "Partner A"
    label_b = raw_b.strip() or "Partner B"

    # Back button
    back_col, _, _ = st.columns([1, 3, 3])
    with back_col:
        if st.button("🔙 Back to edit statements"):
            st.session_state.view = "input"
            st.rerun()

    # --------- CSS FOR CENTERED CARD + BUBBLES ---------
    st.markdown(
        """
        <style>
        .center-wrapper {
            display: flex;
            justify-content: center;
            align-items: flex-start;
        }
        .verdict-card {
            max-width: 950px;
            width: 100%;
            background-color: #ffffff;
            border-radius: 22px;
            padding: 2.5rem 3rem;
            box-shadow: 0 16px 40px rgba(0,0,0,0.10);
            border: 1px solid #e8e8e8;
            font-size: 0.98rem;
            line-height: 1.6;
        }
        .verdict-title {
            text-align: center;
            font-size: 1.8rem;
            font-weight: 800;
            margin-bottom: 0.4rem;
        }
        .verdict-subtitle {
            text-align: center;
            font-size: 0.95rem;
            color: #666666;
            margin-bottom: 1.6rem;
        }
        .split-banner {
            text-align: center;
            font-size: 1.2rem;
            font-weight: 750;
            padding: 0.9rem 1.2rem;
            margin-bottom: 1.0rem;
            border-radius: 999px;
            background: linear-gradient(135deg, #fff3da, #ffd9b5);
            border: 1px solid #f0c892;
        }
        .bubble-box {
            background: #fffaf0;
            border-radius: 14px;
            padding: 0.9rem 1.1rem;
            border: 1px solid #f0cf9b;
            margin-bottom: 1.4rem;
        }
        .bubble-box-grey {
            background: #f6f7fb;
            border-radius: 14px;
            padding: 0.9rem 1.1rem;
            border: 1px solid #dde1f0;
            margin-bottom: 1.4rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # --------- LOADING WITH GIF (4s) ---------
    if not st.session_state.verdict_revealed:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("### 🐧 The Penguin is delivering the verdict...")
            st.image("penguin_gavel.gif", use_column_width=True)
            st.caption("Please wait a few seconds while the gavel comes down and the verdict is written.")
        time.sleep(4)
        st.session_state.verdict_revealed = True
        st.rerun()

    # --------- PARSE VERDICT TEXT ---------
    verdict_text = st.session_state.verdict_md or ""

    summary_section = extract_section(
        verdict_text,
        "## 📝 Case summary",
        ["## 💗 Partner A – feelings & needs", "## 💗 Partner B – feelings & needs",
         "## ⚖️ Responsibility split", "## 🔧", "## 💬", "##"]
    )

    responsibility_section = extract_section(
        verdict_text,
        "## ⚖️ Responsibility split",
        ["## 💬", "## 🔧", "## 💗 Partner A – feelings & needs", "## 💗 Partner B – feelings & needs", "## 📝", "##"]
    )

    partner_a_section = extract_section(
        verdict_text,
        "## 💗 Partner A – feelings & needs",
        ["## 💗 Partner B – feelings & needs", "## ⚖️ Responsibility split", "## 🔧", "## 💬", "##"]
    )

    partner_b_section = extract_section(
        verdict_text,
        "## 💗 Partner B – feelings & needs",
        ["## ⚖️ Responsibility split", "## 🔧", "## 💬", "##"]
    )

    improve_section = extract_section(
        verdict_text,
        "## 🔧 How both of you can improve",
        ["## 💬", "##"]
    )

    examples_section = extract_section(
        verdict_text,
        "## 💬 Example sentences you could say to each other",
        ["##"]
    )

    # Clean bullets
    responsibility_section = clean_empty_bullets(responsibility_section)
    partner_a_section = clean_empty_bullets(partner_a_section)
    partner_b_section = clean_empty_bullets(partner_b_section)
    improve_section = clean_empty_bullets(improve_section)
    examples_section = clean_empty_bullets(examples_section)

    # Split & map
    overall_split_line, responsibility_reason = split_overall_and_reason(responsibility_section)
    improve_a, improve_b = split_by_partner_markers(improve_section, "For Partner A", "For Partner B")
    examples_a, examples_b = split_by_partner_markers(examples_section, "For Partner A", "For Partner B")

    # ---- Replace "Partner A/B" with real names for DISPLAY ----
    def replace_labels(text: str) -> str:
        if not text:
            return ""
        return (text
                .replace("Partner A", label_a)
                .replace("partner a", label_a)
                .replace("Partner B", label_b)
                .replace("partner b", label_b))

    overall_split_line_disp = replace_labels(overall_split_line)
    responsibility_reason_disp = replace_labels(responsibility_reason)
    partner_a_disp = replace_labels(partner_a_section)
    partner_b_disp = replace_labels(partner_b_section)
    improve_a_disp = replace_labels(improve_a)
    improve_b_disp = replace_labels(improve_b)
    examples_a_disp = replace_labels(examples_a)
    examples_b_disp = replace_labels(examples_b)

    # --------- RENDER CENTERED CARD ---------
    st.markdown("<div class='center-wrapper'><div class='verdict-card'>", unsafe_allow_html=True)

    st.markdown(
        """
        <div class="verdict-title">Penguin Judge – Verdict Document</div>
        <div class="verdict-subtitle">A gentle but honest view of what happened and how you both can grow.</div>
        """,
        unsafe_allow_html=True,
    )

    # Summary
    if summary_section:
        st.markdown("### 📝 Case summary")
        st.markdown(summary_section)

    # Big centered split
    if overall_split_line_disp:
        st.markdown(f"<div class='split-banner'>{overall_split_line_disp}</div>", unsafe_allow_html=True)

    # Why split makes sense in yellow bubble
    if responsibility_reason_disp:
        html_reason = section_to_html(responsibility_reason_disp)
        st.markdown("#### Why this split makes sense")
        st.markdown(f"<div class='bubble-box'>{html_reason}</div>", unsafe_allow_html=True)

    # Feelings side-by-side
    st.markdown("### 💗 How each of you is feeling")
    f_left, f_right = st.columns(2)
    with f_left:
        st.markdown(f"#### {label_a} – feelings & needs")
        html_a = section_to_html(partner_a_disp or "_No details found._")
        st.markdown(f"<div class='bubble-box-grey'>{html_a}</div>", unsafe_allow_html=True)
    with f_right:
        st.markdown(f"#### {label_b} – feelings & needs")
        html_b = section_to_html(partner_b_disp or "_No details found._")
        st.markdown(f"<div class='bubble-box-grey'>{html_b}</div>", unsafe_allow_html=True)

    # Improvements side-by-side
    if improve_section:
        st.markdown("---")
        st.markdown("### 🔧 How both of you can improve")
        i_left, i_right = st.columns(2)
        with i_left:
            st.markdown(f"#### {label_a}")
            html_improve_a = section_to_html(improve_a_disp or "_No specific suggestions._")
            st.markdown(f"<div class='bubble-box-grey'>{html_improve_a}</div>", unsafe_allow_html=True)
        with i_right:
            st.markdown(f"#### {label_b}")
            html_improve_b = section_to_html(improve_b_disp or "_No specific suggestions._")
            st.markdown(f"<div class='bubble-box-grey'>{html_improve_b}</div>", unsafe_allow_html=True)

    # Examples side-by-side
    if examples_section:
        st.markdown("---")
        st.markdown("### 💬 Example sentences you could say to each other")
        e_left, e_right = st.columns(2)
        with e_left:
            st.markdown(f"#### {label_a}")
            html_ex_a = section_to_html(examples_a_disp or "_No example sentences._")
            st.markdown(f"<div class='bubble-box-grey'>{html_ex_a}</div>", unsafe_allow_html=True)
        with e_right:
            st.markdown(f"#### {label_b}")
            html_ex_b = section_to_html(examples_b_disp or "_No example sentences._")
            st.markdown(f"<div class='bubble-box-grey'>{html_ex_b}</div>", unsafe_allow_html=True)

    if not verdict_text:
        st.info("No verdict yet. Please go back and submit your statements.")

    st.markdown("</div></div>", unsafe_allow_html=True)
