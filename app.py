from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from io import BytesIO
import os
import openai
import fitz  # PyMuPDF
import PyPDF2
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
from docx import Document
import re

load_dotenv()
app = Flask(__name__)
CORS(app)

LABEL_KEYWORDS = {
    'date': "daily lesson plan date",
    'standards': "missouri learning standard",
    'objectives': "learning targets",
    'wida': "wida standard",
    'language_obj': "language objective",
    'materials': "materials",
    'vocabulary': "vocabulary",
    'assessment': "lesson assessment",
    'success_criteria': "criteria for success",
    'do_now': "do now",
    'i_do': "i do",
    'we_do': "we do",
    'you_do_together': "you do together",
    'you_do_alone': "you do alone",
    'homework': "homework"
}

SLPS_COORDINATES = {
    'date': (100, 720),
    'standards': (100, 685),
    'objectives': (320, 685),
    'wida': (100, 650),
    'language_obj': (320, 650),
    'materials': (100, 615),
    'vocabulary': (320, 615),
    'assessment': (100, 580),
    'success_criteria': (320, 580),
    'do_now': (_
