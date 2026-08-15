#!/usr/bin/env python3
"""Regenerate the detailed UC05 agenda PDF fixture."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "input" / "project_nimbus_agenda.pdf"
PAGE_W, PAGE_H = A4


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#1F4E78"))
    canvas.rect(0, PAGE_H - 20 * mm, PAGE_W, 20 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(18 * mm, PAGE_H - 12.5 * mm, "PROJECT NIMBUS - PILOT READINESS REVIEW")
    canvas.setFillColor(colors.HexColor("#566573"))
    canvas.setFont("Helvetica", 8)
    canvas.drawString(18 * mm, 12 * mm, "Internal working document - proposed items require meeting confirmation")
    canvas.drawRightString(PAGE_W - 18 * mm, 12 * mm, f"Page {doc.page}")
    canvas.restoreState()


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=28 * mm, bottomMargin=20 * mm, title="Project Nimbus Pilot Readiness Review Agenda")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=header_footer)])
    styles = getSampleStyleSheet()
    title = ParagraphStyle("Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=colors.HexColor("#17365D"), alignment=TA_LEFT, spaceAfter=10)
    subtitle = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=10, leading=14, textColor=colors.HexColor("#566573"), spaceAfter=10)
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=colors.HexColor("#1F4E78"), spaceBefore=6, spaceAfter=8)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#2F5597"), spaceBefore=5, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=9.5, leading=14, spaceAfter=6)
    note = ParagraphStyle("Note", parent=body, backColor=colors.HexColor("#FFF2CC"), borderColor=colors.HexColor("#D6B656"), borderWidth=0.5, borderPadding=7, spaceBefore=5, spaceAfter=10)
    small = ParagraphStyle("Small", parent=body, fontSize=8.5, leading=12)

    def wrap_rows(data):
        return [data[0]] + [[Paragraph(str(cell), small) for cell in row] for row in data[1:]]

    story = [
        Spacer(1, 8 * mm),
        Paragraph("Project Nimbus Pilot Readiness Review", title),
        Paragraph("Agenda and pre-read | 17 September 2026 | 09:00-09:30 | Online meeting", subtitle),
        Paragraph("Document status", h1),
        Paragraph("This agenda records proposals and questions prepared before the meeting. It is not an approved decision record. Decisions, owners, dates, and approvals must be confirmed from the spoken meeting and documented with evidence.", note),
        Paragraph("Meeting purpose", h1),
        Paragraph("Assess whether the Project Nimbus customer-service pilot is ready to proceed, agree the pilot scope and controls, assign readiness actions, and identify matters that require decisions outside the project team.", body),
        Paragraph("Expected outcomes", h1),
        Table(wrap_rows([
            [Paragraph("Outcome", small), Paragraph("Expected meeting result", small)],
            ["Pilot scope", "Confirm the participating team, approximate user group, duration, and target start date."],
            ["Data protection", "Confirm permitted data and identify any required assessment or approval."],
            ["Procurement", "Confirm quotation review actions and clarify whether the budget can be approved."],
            ["Readiness", "Assign training, sandbox, support, and go/no-go preparation actions."],
            ["Open risks", "Record unresolved SSO, budget, or ownership questions without inferring decisions."],
        ]), colWidths=[42 * mm, 120 * mm], repeatRows=1, style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#17365D")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("LEADING", (0, 0), (-1, -1), 12),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#AAB7C4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FB")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])),
        Spacer(1, 6 * mm),
        Paragraph("Participants", h1),
        Table(wrap_rows([
            ["Name", "Role", "Meeting responsibility"],
            ["Elena Markovic", "Project Manager", "Chair; final reviewer"],
            ["Liam Chen", "Technical Lead", "Technical readiness and SSO"],
            ["Sofia Niemi", "Data Protection Specialist", "Data protection conditions"],
            ["Arjun Patel", "Project Coordinator", "Coordination and record preparation"],
            ["Mia Roberts", "Procurement Specialist", "Supplier quotation review"],
        ]), colWidths=[43 * mm, 50 * mm, 69 * mm], repeatRows=1, style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.2), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#AAB7C4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FB")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])),
        PageBreak(),
        Spacer(1, 4 * mm),
        Paragraph("Detailed agenda", title),
        Paragraph("Proposed timings support facilitation only. Any proposal below remains unconfirmed until explicitly decided in the meeting.", note),
    ]

    agenda_rows = [
        ["Time", "Topic", "Pre-read context", "Decision or output sought"],
        ["09:00", "1. Opening and attendance", "Confirm participants and purpose.", "Confirm meeting identity and attendance."],
        ["09:03", "2. Pilot scope", "Initial plan: customer-service pilot with a limited user group. Proposed launch: 15 October 2026.", "Agree team, user count, duration, and start date."],
        ["09:08", "3. Data protection", "Clarify whether real customer records are required and whether a DPIA is needed.", "Agree permitted data and assign any assessment."],
        ["09:13", "4. Procurement and budget", "Three supplier quotations expected. Draft budget ceiling: EUR 18,000, pending finance confirmation.", "Assign quotation comparison. Confirm whether budget approval is possible."],
        ["09:18", "5. Training and readiness", "Training, sandbox testing, support material, and a go/no-go summary are required before launch.", "Assign actions, owners, and dates where agreed."],
        ["09:24", "6. Open technical risks", "SSO approach requires architecture-board input.", "Record any decision or leave the matter unresolved."],
        ["09:28", "7. Recap and close", "Review decisions, actions, unresolved matters, and conflicts.", "Confirm the record for manager review."],
    ]
    story.append(Table(wrap_rows(agenda_rows), colWidths=[18 * mm, 37 * mm, 65 * mm, 48 * mm], repeatRows=1, style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.8), ("LEADING", (0, 0), (-1, -1), 11),
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#AAB7C4")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6F9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])))
    story.extend([
        Spacer(1, 6 * mm),
        Paragraph("Important pre-read qualifications", h1),
        Paragraph("The 15 October launch date and EUR 18,000 ceiling are proposals, not approvals. The meeting record must distinguish planned agenda content from spoken decisions. The architecture board, finance function, and support team are not represented as meeting participants unless explicitly stated in the participant list.", body),
        Paragraph("Evidence expectation", h1),
        Paragraph("The final record should allow reviewers to trace agenda-derived context to this document by page number and spoken decisions or actions to the meeting recording by timestamp.", body),
        PageBreak(),
        Spacer(1, 4 * mm),
        Paragraph("Facilitator checklist and record template", title),
        Paragraph("Use this page to guide the discussion. Blank fields do not imply a decision, owner, or date.", note),
        Paragraph("Decision checklist", h1),
        Table(wrap_rows([
            ["Question", "Status before meeting", "Evidence required in final record"],
            ["What is the approved pilot scope?", "Open", "Spoken decision with timestamp"],
            ["What is the approved pilot start date?", "15 October proposed only", "Spoken decision; record conflict if changed"],
            ["What data may be used?", "Open", "Spoken decision with timestamp"],
            ["Is the budget approved?", "Finance confirmation pending", "Do not claim approval without explicit statement"],
            ["Which SSO approach is selected?", "Architecture-board input pending", "Leave unresolved unless explicitly decided"],
        ]), colWidths=[62 * mm, 48 * mm, 58 * mm], repeatRows=1, style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 8.2),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#AAB7C4")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FB")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])),
        Spacer(1, 8 * mm),
        Paragraph("Action-item capture guidance", h1),
        Paragraph("For each action, capture the task, owner, due date, uncertainty reason, and evidence. If an owner or date is not explicitly agreed, leave it null and explain the uncertainty. Do not assign an action to the person who merely raised the topic.", body),
        Spacer(1, 4 * mm),
        Table([
            ["Action", "Owner", "Due date", "Uncertainty", "Evidence"],
            ["", "", "", "", ""], ["", "", "", "", ""], ["", "", "", "", ""], ["", "", "", "", ""],
        ], colWidths=[51 * mm, 33 * mm, 27 * mm, 33 * mm, 24 * mm], repeatRows=1, rowHeights=[8 * mm, 12 * mm, 12 * mm, 12 * mm, 12 * mm], style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#AAB7C4")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])),
        Spacer(1, 8 * mm),
        Paragraph("Review and approval", h1),
        Paragraph("The generated record remains pending review until the project manager approves it. If returned, the coordinator may correct the record or upload corrected source material before processing and review repeat.", body),
    ])
    doc.build(story)
    print(OUTPUT)


if __name__ == "__main__":
    main()
