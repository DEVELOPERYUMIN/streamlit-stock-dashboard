# Copilot Instructions for Streamlit Stock Data Analyzer

## Project Overview
This is a **Streamlit multi-page application** for Korean stock market analysis. The main entry point ([app.py](../app.py)) provides stock price visualization and Excel export functionality. Additional pages are organized in the `pages/` directory.

## Key Architecture & Patterns

### 1. **Streamlit Multi-Page Structure**
- **Main app:** [app.py](../app.py) - Stock data retrieval and visualization entry point
- **Pages directory:** [pages/](../pages/) - Additional pages auto-discovered by Streamlit
- **File naming convention:** Prefix filenames with numbers (e.g., `1-page1.py`, `2-page2.py`) to control sidebar menu order
- **Important:** Files in `pages/` directory automatically become sidebar navigation items in numeric order

### 2. **Core Functional Pattern in app.py**
The workflow uses a strict pattern for Korean stock analysis:
1. **Data Retrieval:** `get_krx_company_list()` fetches listed companies from KRX (Korea Exchange)
2. **Code Resolution:** `get_stock_code_by_company()` accepts either company names or 6-digit stock codes
3. **Data Fetching:** `FinanceDataReader` library retrieves historical price data
4. **Visualization:** Matplotlib with `koreanize_matplotlib` for Korean font rendering
5. **Export:** BytesIO + openpyxl for Excel file downloads

### 3. **Encoding & Localization**
- Korean company data uses **EUC-KR encoding** from KRX source (not UTF-8)
- Use `koreanize_matplotlib` for Korean text rendering in plots
- Date format: `MM.DD.YYYY` for user input, `%Y%m%d` for API calls
- All UI strings and messages use Korean text directly

### 4. **UI/Input Patterns**
```python
# Sidebar inputs follow this order:
st.sidebar.text_input()      # Company name or stock code
st.sidebar.date_input()      # Date range selection
st.sidebar.button()          # Trigger analysis

# Main area outputs:
st.subheader()               # Results title
st.dataframe()               # Data display (e.g., tail(10))
st.pyplot()                  # Matplotlib visualizations
st.download_button()         # File export
```

### 5. **Error Handling Convention**
Wrap data retrieval in try-except with Streamlit-specific feedback:
- `st.error()` - Critical failures (data not found, API errors)
- `st.warning()` - User input validation (missing company name)
- `st.info()` - No-data scenarios (empty results)
- `st.spinner()` - Loading state for long operations

### 6. **Data Processing Pattern**
- Import convention: Standard library → Third-party → Streamlit
- Stock data: 6-digit code format (zero-padded with `f'{x:06}'`)
- DataFrame operations: Use `.copy()` when modifying filtered data
- Visualization: Always set figsize and grid for consistency

## Development Workflow

### Running the Application
```bash
streamlit run app.py
```
This auto-loads all pages from the `pages/` directory.

### Adding New Pages
1. Create file in `pages/` directory
2. Prefix with number for menu order (e.g., `3-page3.py`)
3. Import `streamlit as st` - no additional configuration needed
4. Streamlit automatically adds to sidebar navigation

## Key Dependencies & Their Use
- **streamlit:** UI framework and state management
- **pandas:** Data manipulation and Excel export
- **FinanceDataReader:** Korean stock market data retrieval
- **matplotlib + koreanize_matplotlib:** Plotting with Korean font support
- **openpyxl:** Excel file generation

## Important Project-Specific Details
- **No requirements.txt exists** - Document any new dependencies added
- **KRX API:** Uses `http://kind.krx.co.kr` - may have rate limits or require EUC-KR handling
- **Date handling:** Streamlit caches parsed dates; validate format consistency
- **Excel export:** Uses `BytesIO` in-memory object - appropriate for download_button widget
