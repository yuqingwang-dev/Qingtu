"""PDF export functionality for itineraries."""
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
from typing import List
from app.api.schemas import ItineraryResponse, ItineraryDay


def generate_pdf(itinerary: ItineraryResponse) -> BytesIO:
    """Generate a PDF document from an itinerary."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#4F46E5'),
        spaceAfter=30,
        alignment=TA_CENTER,
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#1E293B'),
        spaceAfter=12,
        spaceBefore=12,
    )
    
    # Title
    story.append(Paragraph("Qingtu Travel Itinerary", title_style))
    story.append(Spacer(1, 0.2 * inch))
    
    # Summary
    story.append(Paragraph("Trip Summary", heading_style))
    summary_data = [
        ["Total Cost", f"${itinerary.summary.total_cost:.2f}"],
        ["Average per Day", f"${itinerary.summary.avg_cost_per_day:.2f}"],
        ["Pace", itinerary.summary.pace_label],
        ["Confidence", f"{(itinerary.confidence_score * 100):.0f}%"],
    ]
    summary_table = Table(summary_data, colWidths=[3 * inch, 2 * inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F1F5F9')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.3 * inch))
    
    # Days
    for day_idx, day in enumerate(itinerary.days, 1):
        from datetime import datetime
        date_obj = datetime.fromisoformat(day.date.replace('Z', '+00:00'))
        date_str = date_obj.strftime('%A, %B %d, %Y')
        
        story.append(Paragraph(f"Day {day_idx}: {date_str}", heading_style))
        story.append(Paragraph(
            f"Total Cost: ${day.total_cost:.2f} | Duration: {day.total_duration_minutes // 60}h {day.total_duration_minutes % 60}m",
            styles['Normal']
        ))
        story.append(Spacer(1, 0.1 * inch))
        
        # Activities table
        activity_data = [["Time", "Activity", "Category", "Cost", "Duration"]]
        for block in day.blocks:
            start_time = datetime.fromisoformat(block.start_time.replace('Z', '+00:00'))
            time_str = start_time.strftime('%I:%M %p')
            activity_data.append([
                time_str,
                block.activity.name,
                block.activity.category,
                f"${block.activity.cost:.2f}",
                f"{block.activity.duration} min"
            ])
        
        activity_table = Table(activity_data, colWidths=[1 * inch, 2.5 * inch, 1 * inch, 0.8 * inch, 0.7 * inch])
        activity_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ]))
        story.append(activity_table)
        story.append(Spacer(1, 0.3 * inch))
    
    # Narrative
    if itinerary.narrative.narrative_text:
        story.append(Paragraph("Itinerary Guide", heading_style))
        story.append(Paragraph(itinerary.narrative.narrative_text, styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

