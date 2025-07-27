from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import openai
import os
from dotenv import load_dotenv  # Required to load .env
from io import BytesIO
import PyPDF2
from reportlab.pdfgen import canvas
import docx
import pdfplumber
import traceback

# Load environment variables from .env file
load_dotenv()  # Ensures your OpenAI key is loaded

app = Flask(__name__)
CORS(app)  # Enable CORS

# Configure OpenAI (will now properly read from .env)
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OpenAI API key not found in .env file!")

def analyze_pdf_template(file_stream):
    """Extract fields from PDF with error handling"""
    try:
        with pdfplumber.open(file_stream) as pdf:
            if not pdf.pages:
                return []
            first_page = pdf.pages[0]
            words = first_page.extract_words() or []
            return [
                {
                    "x": word["x0"],
                    "y": first_page.height - word["top"],
                    "width": word["x1"] - word["x0"],
                    "text": word["text"]
                }
                for word in words 
                if len(word.get("text", "")) < 3
            ]
    except Exception as e:
        print(f"PDF Analysis Error: {e}")
        return []

def fill_pdf_dynamically(file_stream, prompt, fields):
    """Generate AI-filled PDF"""
    try:
        if not openai.api_key:
            raise ValueError("OpenAI key missing!")
        
        ai_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"Fill these fields: {fields}"},
                {"role": "user", "content": prompt}
            ]
        )
        ai_text = ai_response.choices[0].message.content

        packet = BytesIO()
        can = canvas.Canvas(packet)
        for field in fields:
            can.drawString(field["x"], field["y"], ai_text)
        can.save()

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
    except Exception as e:
        print(f"PDF Fill Error: {e}")
        raise

@app.route('/process', methods=['POST'])
def process():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    prompt = request.form.get('prompt', '').strip()

    if not prompt:
        return jsonify({"error": "Prompt cannot be empty"}), 400

    try:
        file_ext = file.filename.rsplit('.', 1)[-1].lower()
        if file_ext == 'pdf':
            fields = analyze_pdf_template(file)
            file.stream.seek(0)
            filled_file, mimetype = fill_pdf_dynamically(file, prompt, fields)
            download_name = "lesson_plan.pdf"
        elif file_ext == 'docx':
            filled_file, mimetype = fill_docx_dynamically(file, prompt)
            download_name = "lesson_plan.docx"
        else:
            return jsonify({"error": "Unsupported file type (use PDF/DOCX)"}), 400

        return send_file(
            filled_file,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name
        )
    except Exception as e:
        traceback.print_exc()  # Log full error to console
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
