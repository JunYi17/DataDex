# 📚 DataDex

**An offline Retrieval-Augmented Generation (RAG) tool for hardware and firmware engineers**

> Keep your proprietary datasheets secure, searchable, and instantly accessible—no cloud uploads, no internet dependency.

---

## 🎯 What is DataDex?

DataDex is an MCP server for Claude Code that transforms your hardware documentation into queryable knowledge. Ingest datasheets, programming guides, and register tables once—then ask natural language questions across all your documentation instantly.

Powered by **local embeddings** and **vector search**, DataDex keeps everything offline and secure—no data leaves your machine.

---

## 👥 Who Is It For?

**Embedded software and firmware engineers** who spend countless hours cross-referencing datasheets, register maps, and protocol specifications during development.

If you're tired of:
- ❌ Manually scanning through hundreds of PDF pages
- ❌ Uploading sensitive documentation to cloud services
- ❌ Losing context switching between multiple reference documents
- ❌ Forgetting register addresses and bit-field definitions

...then DataDex is for you.

---

## ✨ Key Features

### 🔍 **Semantic Document Search**
Ask natural language questions across all ingested datasheets and programming guides. No keyword matching—real understanding.

### 📋 **Register Lookup**
Query any register by name or address and instantly get:
- Full bit-field breakdown
- Access type (R/W/RO)
- Reset values
- Constraints and dependencies

### 📖 **Topic Summaries**
Get concise overviews of features or protocols without reading the entire document. Perfect for getting up to speed on unfamiliar chips.

### 🏢 **Multi-Workspace Support**
Organize documents by chip, product, or project. Switch contexts seamlessly without reloading data.

### 📦 **Broad Format Support**
Ingest documents in your native formats:
- 📄 `.docx` (Word documents)
- 📕 `.pdf` (PDFs)
- 📊 `.xlsx` (Spreadsheets)
- 📝 `.md` (Markdown)

---

## 🚀 Common Use Cases

| Use Case | Benefit |
|----------|---------|
| 🔌 **Peripheral Configuration** | Ask how to configure I2C, SPI, or GPIO—get the exact register sequence without hunting through the programming guide |
| ⚙️ **Register Bit-Field Lookup** | Query registers while writing driver code; get instant access to fields, widths, and constraints |
| 📋 **Spec-to-Register Mapping** | Map functional requirements from datasheets directly to register sequences |
| 🧠 **Rapid Onboarding** | Get up to speed on unfamiliar chips in minutes instead of hours |

---

## 🤝 Get Started

Refer to the guide - GettingStart.txt

---

**Keep your hardware docs local. Keep your work fast. Keep your secrets safe.**

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

## 👤 Author

Built by [Jun Yi Lee](https://github.com/JunYi17)
