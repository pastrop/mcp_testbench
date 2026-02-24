# Current State - Quick Reference

**Last Updated**: 2026-01-27

## System Status: ✅ Production Ready

## Current Configuration

- **AI Model**: `claude-haiku-4-5-20251001` (Haiku 4.5)
- **Backend**: FastAPI on port 8000
- **Frontend**: React + Vite on port 5173
- **Contracts**: 25 JSON files in `data/Parsed_Contracts/`

## Start Commands

```bash
# Backend (auto-stops old processes)
cd /Users/alexsmirnoff/Documents/src/testbench/ui_renderer
./run_backend.sh

# Frontend
cd frontend && npm run dev
```

## Recent Critical Fixes (Session 2026-01-27)

### 1. Table Component Data Binding ✅
- **Issue**: Tables showed "No data available"
- **Cause**: Claude generated `rows` prop, Table expects `data` prop
- **Fixed**: System prompt now explicitly requires `data` prop
- **Location**: `backend/app/services/ai_service.py` lines 30-37

### 2. KeyValueList Component Data Binding ✅
- **Issue**: KeyValueList showed "No data available"
- **Cause**: Data paths nested in props instead of data_bindings
- **Fixed**: Explicit binding pattern in system prompt
- **Location**: `backend/app/services/ai_service.py` lines 33-37

### 3. Backend Startup Script ✅
- **Issue**: "Address already in use" errors
- **Fixed**: Auto-cleanup of port 8000 in `run_backend.sh`
- **Now**: Script is idempotent, safe to run repeatedly

## Component Prop Names (IMPORTANT!)

These are critical - AI must use exact prop names:

| Component | Array/Object Prop | Notes |
|-----------|------------------|-------|
| Table | `data` | NOT `rows` or `dataSource` |
| KeyValueList | `items` | Bind entire object/array |
| BadgeList | `items` | Array of strings |
| Grid | `columns` | Number of columns |
| Tabs | `tabs` | Array of tab objects |

## Data Binding Pattern

**Correct**:
```json
{
  "type": "Table",
  "props": { "columns": [...] },
  "data_bindings": {
    "data": { "path": "fees_and_rates" }
  }
}
```

**Wrong**:
```json
{
  "type": "Table",
  "props": { "columns": [...] },
  "data_bindings": {
    "rows": { "path": "fees_and_rates" }  // ❌ Wrong prop name
  }
}
```

## Known Working Contracts

- ✅ WEBNORUS_LIMITED_PAYMENT_MANAGEMENT_SERVICES_AGREEMENT.pdf.json
- ✅ Banking General Agreement_AIMSKINZ LIMITED.docx.pdf.json
- ✅ QUANTESSA_LTD.pdf.json
- ✅ All 25 contracts in data folder

## File Locations

### Backend
- Main: `backend/app/main.py`
- AI Service: `backend/app/services/ai_service.py` ⚠️ Critical file
- Config: `backend/app/core/config.py`
- Routes: `backend/app/api/routes.py`

### Frontend
- Renderer: `frontend/src/lib/Renderer.jsx` ⚠️ Critical file
- Components: `frontend/src/components/` (15 components)
- API Client: `frontend/src/lib/api.js`

### Documentation
- **SESSION_LOG.md** ← Read this for detailed session history
- **PROJECT_SUMMARY.md** ← Read this for system overview
- **QUICKSTART.md** ← Read this for setup instructions

## Troubleshooting Quick Reference

### Backend won't start
```bash
lsof -ti:8000 | xargs kill -9
./run_backend.sh
```

### API key issues
- Unset environment variable: `unset ANTHROPIC_API_KEY`
- Check `.env` file has correct key
- Restart backend after changing key

### Data not displaying
1. Check component prop name matches expected (see table above)
2. Check data_bindings path is correct
3. Check contract JSON structure matches path
4. Look in browser console for binding errors

### Test specific contract
```bash
curl -X POST "http://localhost:8000/api/v1/generate-ui?filename=FILENAME.json"
```

## Git Status

- **Ignored**: `data/`, `.env`, `.venv`, `node_modules`, IDE folders
- **Root .gitignore**: Consolidated, manages all subdirectories
- **No nested .gitignore files**: Removed for simplicity

## Next Session Checklist

1. [ ] Read SESSION_LOG.md to see what was done last time
2. [ ] Check if backend/frontend are already running (port 8000/5173)
3. [ ] Pull latest changes if working with others
4. [ ] Verify API key is in backend/.env
5. [ ] Test with one contract before making changes

## AI Prompt Engineering Notes

### What Works
- ✅ Explicit prop name requirements with examples
- ✅ CORRECT vs WRONG examples in prompts
- ✅ Tool-based structured output (sync method)
- ✅ Prefill technique for JSON reliability (async method)

### What Doesn't Work
- ❌ Assuming AI knows component APIs
- ❌ Vague instructions like "use appropriate props"
- ❌ Single-point instruction (needs reinforcement)

## Performance Notes

- **Haiku 4.5**: ~2-3 seconds per UI generation
- **Tool-based output**: Most reliable, use for production
- **Prefill technique**: Backup method, also reliable
- **Caching**: Not implemented yet, future enhancement

---

**📝 For detailed history**: See [SESSION_LOG.md](./SESSION_LOG.md)
**📚 For system overview**: See [PROJECT_SUMMARY.md](./PROJECT_SUMMARY.md)
**🚀 For setup guide**: See [QUICKSTART.md](./QUICKSTART.md)
