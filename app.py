from flask import Flask, request, send_file
import openai
import os
from io import BytesIO
import PyPDF2
from reportlab.pdfgen import canvas
import docx
from docx.shared import Pt
import pdfplumber  # For smarter PDF analysis

app = Flask(__name__)

# Configure OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

def analyze_pdf_template(file_stream):
    """Auto-detect editable fields in PDF"""
    fields = []
    with pdfplumber.open(file_stream) as pdf:
        first_page = pdf.pages[0]
        
        # Detect text boxes (customize thresholds as needed)
        for word in first_page.extract_words():
            if len(word["text"]) < 3:  # Likely a field label
                fields.append({
                    "x": word["x0"],
                    "y": first_page.height - word["top"],  # Convert to bottom-left origin
                    "width": word["x1"] - word["x0"],
                    "text": word["text"]
                })
    return fields

def fill_pdf_dynamically(file_stream, prompt, fields):
    """Fill detected PDF fields with AI content"""
    # Generate AI content for each field
    ai_response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": f"Fill these template fields based on the prompt. Fields: {fields}"},
            {"role": "user", "content": prompt}
        ]
    )
    ai_text = ai_response.choices[0].message.content

    # Create a new PDF layer with filled text
    packet = BytesIO()
    can = canvas.Canvas(packet)
    
    for field in fields:
        can.drawString(field["x"], field["y"], ai_text)  # Fill detected positions
    
    can.save()

    # Merge with original PDF
    packet.seek(0)
    new_pdf = PyPDF2.PdfReader(packet)
    original_pdf = PyPDF2.PdfReader(file_stream)
    output = PyPDF2.PdfWriter()

    page = original_pdf.pages[0]
    page.merge_page(new_pdf.pages[0])
    output.add_page(page)

    output_stream = BytesIO()
    output.write(output_stream)
    output_stream.seek(0)
    return output_stream, "application/pdf"

def fill_docx_dynamically(file_stream, prompt):
    """Fill all paragraphs in DOCX (no fixed placeholders needed)"""
    doc = docx.Document(file_stream)
    
    # Generate AI content
    ai_response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Fill this lesson plan template:"},
            {"role": "user", "content": prompt}
        ]
    )
    ai_text = ai_response.choices[0].message.content

    # Fill empty paragraphs or short placeholder text
    for paragraph in doc.paragraphs:
        if len(paragraph.text) < 5:  # Fill short/empty fields
            paragraph.text = ai_text
            paragraph.style = "Normal"  # Preserve formatting
    
    output_stream = BytesIO()
    doc.save(output_stream)
    output_stream.seek(0)
    return output_stream, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

@app.route('/process', methods=['POST'])
def process():
    if 'file' not in request.files:
        return {"error": "No file uploaded"}, 400
    
    file = request.files['file']
    prompt = request.form.get('prompt', '')
    file_ext = file.filename.split('.')[-1].lower()
    
    try:
        if file_ext == 'pdf':
            fields = analyze_pdf_template(file)
            file.stream.seek(0)  # Reset stream after analysis
            filled_file, mimetype = fill_pdf_dynamically(file, prompt, fields)
            download_name = "filled_template.pdf"
        elif file_ext == 'docx':
            filled_file, mimetype = fill_docx_dynamically(file, prompt)
            download_name = "filled_template.docx"
        else:
            return {"error": "Unsupported file type"}, 400
        
        return send_file(
            filled_file,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name
        )
    except Exception as e:
        return {"error": str(e)}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
        )
    except Exception as e:
        return {"error": str(e)}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
