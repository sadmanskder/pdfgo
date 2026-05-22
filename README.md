# PDFGo

AI-powered PDF study companion for students. Read PDFs, get instant explanations, generate summaries, ask questions from visible content, and reduce context switching between browser tabs, notes, and AI tools.

Designed as a desktop study environment where PDF reading and AI assistance happen side-by-side.

---

## Features

### Smart PDF Reading
- Open and read PDF documents inside the app
- Smooth scrolling and zoom support
- Student-focused reading experience

### AI Explanation Panel
- Automatic explanation of visible PDF content
- Simplifies difficult textbook language
- Converts complex academic concepts into easier explanations

### Ask Questions
Ask questions directly from the current page:

Examples:

> "Explain this paragraph simply"  
> "What is glycolysis?"  
> "Summarize this mechanism"  
> "Create exam questions from this page"

---

### Auto Summary Generation
Generate:

- Quick summaries
- Key points
- Important concepts
- Exam preparation notes

---

### Quiz Generation
Generate multiple choice questions from current content:

- MCQs
- Correct answers
- Explanations
- Self-testing

---

### Image / Diagram Understanding
Supports understanding:

- Scientific figures
- Charts
- Graphs
- Biological pathways
- Diagrams

---

### Student-Centered Workflow

Traditional workflow:

PDF → Browser → Search → AI → Notes → Back to PDF

PDFGo workflow:

PDF → Read → Understand → Ask → Continue

---

## Screenshots

Add screenshots after publishing:

```md
![Main UI](screenshots/main.png)

![AI Panel](screenshots/ai-panel.png)

![Summary Example](screenshots/summary.png)
```

---

## Tech Stack

Frontend/Desktop:

- Python
- PyQt6 / PySide6 *(depending on implementation)*

PDF Processing:

- PyMuPDF
- PDF rendering libraries

Backend:

- PHP API
- JSON communication

AI Layer:

- External LLM API integration
- Text understanding
- Image understanding
- Summaries
- Quiz generation

---

## Installation

Clone repository:

```bash
git clone https://github.com/USERNAME/pdfgo.git
cd pdfgo
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run application:

```bash
python main.py
```

---

## Configuration

Create environment variables or server configs:

Example:

```env
AI_API_KEY=your_key
AI_MODEL=your_model
API_ENDPOINT=https://yourdomain.com/api/
```

Do NOT commit real API keys.

---

## Folder Structure

Example:

```txt
pdfgo/

├── main.py
├── splash.py
├── intro.py
├── requirements.txt
├── assets/
│      ├── icons/
│      ├── logos/
│      └── images/
│
├── api/
│      └── index.php
│
├── screenshots/
│
└── README.md
```

---

## Planned Features

Roadmap:

### UI / Experience

- [ ] VS Code inspired interface
- [ ] Better dark theme
- [ ] Custom title bar
- [ ] Multi-tab PDFs

### AI

- [ ] Chat memory
- [ ] Citation support
- [ ] Flashcard generation
- [ ] Research paper simplification
- [ ] Note generation
- [ ] Equation explanations

### Study Tools

- [ ] Highlight saving
- [ ] Annotation support
- [ ] Bookmarks
- [ ] Revision mode
- [ ] Exam mode

### Productivity

- [ ] Offline support
- [ ] Local AI support
- [ ] Export notes
- [ ] Sync study sessions

---

## Target Users

PDFGo is built mainly for:

- University students
- Biology students
- Biotechnology students
- Medical students
- Researchers
- STEM learners
- Competitive exam students

---

## Motivation

Many students read PDFs while constantly switching between:

- Browser
- Search engine
- AI tools
- Notes
- Lecture slides

PDFGo attempts to reduce this friction by merging reading and understanding into one workspace.

---

## Security

Never expose:

- API keys
- Database credentials
- Environment variables

Use:

```gitignore
.env
config.php
secret/
```

---

## Contributing

Contributions are welcome.

Possible areas:

- UI improvements
- Performance optimization
- PDF rendering
- AI integration
- Bug fixing
- Accessibility

Fork repository → Create branch → Commit → Open Pull Request

---

## Known Limitations

Current limitations may include:

- Large PDFs may slow responses
- Rate limits from AI providers
- Complex diagrams may require manual interpretation

---

## License

Choose a license before production release.

Recommended:

MIT License

or

Apache 2.0

---

## Author

**Sadman Sikder**  
Biochemistry & Biotechnology Student  
Developer of PDFGo

GitHub:

```txt
https://github.com/YOUR_USERNAME
```

---

# Future Vision

PDFGo aims to become:

> "A study workspace where reading, understanding, questioning and revising happen in one place."
