from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import openai
import os
from io import BytesIO
import PyPDF2
from reportlab.pdfgen import canvas
import docx
from docx.shared import Pt
import pdfplumber
import traceback

app = Flask(__name__)
# Configure CORS to allow only your Webflow domain
CORS(app, resources={
    r"/process": {
        "origins": ["https://t1tan-tech.webflow.io"],
        "methods": ["POST"],
        "allow_headers": ["Content-Type"]
    }
})

# Configure OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

def analyze_pdf_template(file_stream):
    """Detect editable fields in PDF with error handling"""
    try:
        with pdfplumber.open(file_stream) as pdf:
            if not pdf.pages:
                return []  # No pages in PDF
            
            first_page = pdf.pages[0]
            words = first_page.extract_words() or []  # Handle empty words list
            
            fields = [
                {
                    "x": word["x0"],
                    "y": first_page.height - word["top"],
                    "width": word["x1"] - word["x0"],
                    "text": word["text"]
                }
                for word in words 
                if len(word.get("text", "")) < 3  # Safer dict access
            ]
            return fields
    except Exception as e:
        print(f"PDF Analysis Error: {str(e)}")
        traceback.print_exc()
        return []

def fill_pdf_dynamically(file_stream, prompt, fields):
    """Fill PDF with AI content, with OpenAI validation"""
    try:
        ai_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"Fill these template fields: {fields}"},
                {"role": "user", "content": prompt}
            ]
        )
        if not ai_response.choices:
            raise ValueError("OpenAI returned no completions")
        
        ai_text = ai_response.choices[0].message.content

        # Create filled PDF layer
        packet = BytesIO()
        can = canvas.Canvas(packet)
        for field in fields:
            can.drawString(field["x"], field["y"], ai_text)
        can.save()

        # Merge with original PDF
        packet.seek(0)
        new_pdf = PyPDF2.PdfReader(packet)
        original_pdf = PyPDF2.PdfReader(file_stream)
        
        if not new_pdf.pages or not original_pdf.pages:
            raise ValueError("PDF has no pages to merge")
        
        output = PyPDF2.PdfWriter()
        page = original_pdf.pages[0]
        page.merge_page(new_pdf.pages[0])
        output.add_page(page)

        output_stream = BytesIO()
        output.write(output_stream)
        output_stream.seek(0)
        return output_stream, "application/pdf"

    except Exception as e:
        print(f"PDF Fill Error: {str(e)}")
        traceback.print_exc()
        raise

def fill_docx_dynamically(file_stream, prompt):
    """Fill DOCX template with AI content"""
    try:
        doc = docx.Document(file_stream)
        ai_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Fill this template:"},
                {"role": "user", "content": prompt}
            ]
        )
        if not ai_response.choices:
            raise ValueError("OpenAI returned no completions")
        
        ai_text = ai_response.choices[0].message.content

        for paragraph in doc.paragraphs:
            if len(paragraph.text) < 5:  # Fill short/empty fields
                paragraph.text = ai_text
                paragraph.style = "Normal"

        output_stream = BytesIO()
        doc.save(output_stream)
        output_stream.seek(0)
        return output_stream, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    except Exception as e:
        print(f"DOCX Fill Error: {str(e)}")
        traceback.print_exc()
        raise

@app.route('/process', methods=['POST'])
def process():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    prompt = request.form.get('prompt', '').strip()
    
    # Validate file extension
    if not file.filename or '.' not in file.filename:
        return jsonify({"error": "Invalid filename"}), 400
    
    file_ext = file.filename.rsplit('.', 1)[-1].lower()
    if file_ext not in ['pdf', 'docx']:
        return jsonify({"error": "Unsupported file type (only PDF/DOCX)"}), 400
    
    try:
        if file_ext == 'pdf':
            fields = analyze_pdf_template(file)
            file.stream.seek(0)  # Reset stream after analysis
            filled_file, mimetype = fill_pdf_dynamically(file, prompt, fields)
            download_name = "filled_lesson_plan.pdf"
        elif file_ext == 'docx':
            filled_file, mimetype = fill_docx_dynamically(file, prompt)
            download_name = "filled_lesson_plan.docx"
        
        return send_file(
            filled_file,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name
        )
        
    except Exception as e:
        print(f"Process Route Error: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
