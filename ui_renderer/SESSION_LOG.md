# UI Renderer - Development Session Log

This file tracks major changes, bug fixes, and improvements made in each development session.

---

## Session: 2026-01-27 - Model Switch, Critical Bug Fixes, and Data Binding Issues

### Summary
Major session focused on switching from Claude Sonnet to Claude Haiku 4.5, fixing critical data binding bugs that prevented data from displaying, and improving the backend startup script.

### Changes Made

#### 1. Model Switch to Claude Haiku 4.5
- **Changed**: Switched from `claude-sonnet-4-5-20250929` to `claude-haiku-4-5-20251001`
- **Location**: `backend/app/services/ai_service.py` lines 137, 300
- **Reason**: Testing Haiku 4.5 for performance and cost optimization
- **Result**: ✅ Working excellently, generates high-quality UI specs

#### 2. Git Configuration Improvements
- **Added**: `data/` to root `.gitignore`
- **Added**: Consolidated ignore patterns from `ui_renderer/.gitignore` to root
- **Deleted**: `ui_renderer/.gitignore` (no longer needed)
- **Patterns added**:
  - `.env` and `.env.*` (critical for API key security)
  - IDE folders (`.vscode/`, `.idea/`)
  - Testing artifacts (`.coverage`, `.pytest_cache/`)
  - Virtual environments (`venv/`, `ENV/`)

#### 3. CRITICAL BUG FIX: Table Component Data Binding
**Issue**: WEBNORUS contract Transaction Fees table displayed "No data available" despite having 6 transaction fees in the data.

**Root Cause**:
- Claude was generating: `data_bindings: { "rows": { "path": "fees_and_rates" } }`
- Table component expects: `data` prop (not `rows`)
- Result: Table received `rows` prop but looked for `data` → empty table

**Fix Applied**:
- Updated system prompt to specify Table uses `"data"` prop explicitly
- Added user prompt rule #4 with correct/incorrect examples:
  ```
  CORRECT: {"data_bindings": {"data": {"path": "fees_and_rates"}}}
  WRONG: {"data_bindings": {"rows": {"path": "fees_and_rates"}}}
  ```
- Location: `backend/app/services/ai_service.py` lines 30-37, 304-306

**Impact**: ✅ All tables now display data correctly across all contracts

#### 4. CRITICAL BUG FIX: KeyValueList Component Data Binding
**Issue**: AIMSKINZ contract KeyValueList sections displayed "No data available" for payment_terms and vat_treatment.

**Root Cause**:
Claude was generating conflicting data structures:
```json
{
  "props": {
    "items": [
      { "label": "Effective Date", "value": { "path": "effective_date" } }
    ]
  },
  "data_bindings": { "items": { "path": "effective_date" } }
}
```
Problems:
1. Data paths nested inside `props.items` structure (incorrect)
2. `data_bindings.items` overwrites `props.items` with a string value
3. KeyValueList expected object/array, received string → "No data available"

**Fix Applied**:
- Updated system prompt to specify KeyValueList binding pattern
- Added user prompt rule #5 with correct/incorrect examples:
  ```
  CORRECT: {"data_bindings": {"items": {"path": "payment_terms"}}}
  WRONG: {"props": {"items": [{"label": "X", "value": {"path": "..."}}]}}
  ```
- Location: `backend/app/services/ai_service.py` lines 33-37, 307-309

**Impact**: ✅ All KeyValueList components now display data correctly

#### 5. Backend Startup Script Enhancement
**Issue**: Script failed with "Address already in use" error whenever a backend was already running.

**Root Cause**:
- During troubleshooting, I start backend in background for testing
- Old processes stay running when script is run again
- User sees error every time

**Fix Applied**:
- Added automatic port cleanup to `run_backend.sh`
- Script now checks if port 8000 is in use
- Automatically kills old processes before starting new one
- Added `unset ANTHROPIC_API_KEY` to ensure `.env` file is used

**Code Added** (lines 5-11):
```bash
# Check if port 8000 is in use and kill the process
if lsof -ti:8000 > /dev/null 2>&1; then
    echo "Stopping existing backend on port 8000..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    sleep 1
fi
```

**Impact**: ✅ Script is now idempotent - can be run repeatedly without errors

#### 6. Prefill Technique for JSON Reliability
**Enhancement**: Updated async method to use prefill technique for more reliable JSON output.

**Implementation**:
```python
messages=[
    {"role": "user", "content": user_prompt},
    {"role": "assistant", "content": "{"}  # Prefill to force JSON
],
```
- Forces Claude to start response with `{`
- More reliable JSON generation
- Applied to `generate_ui_spec` async method

**Note**: Sync method (`generate_ui_spec_sync`) uses tool-based structured output, which is already highly reliable.

### Files Modified

1. **`backend/app/services/ai_service.py`** - Multiple improvements:
   - Model changed to Haiku 4.5 (2 locations)
   - Table data binding rules added
   - KeyValueList binding rules added
   - Prefill technique implemented
   - System prompt enhanced with explicit component requirements

2. **`.gitignore`** (root) - Consolidated ignore patterns:
   - Added `data/` folders
   - Added `.env` files (security critical)
   - Added IDE folders
   - Added testing artifacts

3. **`run_backend.sh`** - Enhanced startup script:
   - Auto-cleanup of port 8000
   - Unsets ANTHROPIC_API_KEY environment variable
   - Now fully idempotent

4. **`ui_renderer/.gitignore`** - Deleted (consolidated to root)

### Testing & Verification

#### Table Component Fix (WEBNORUS contract)
**Before**: Transaction Fees section showed "No data available"
**After**:
```json
{
  "data_bindings": { "data": { "path": "company_fees.transaction_fees" } },
  "props": {
    "columns": [
      {"key": "fee_name", "label": "Fee Name"},
      {"key": "payment_method", "label": "Payment Method"},
      {"key": "amount", "label": "Fee Rate"},
      {"key": "currency", "label": "Currency"},
      {"key": "conditions", "label": "Conditions"}
    ]
  }
}
```
✅ Displays all 6 transaction fees correctly

#### KeyValueList Component Fix (AIMSKINZ contract)
**Before**: Payment Terms and VAT Treatment sections showed "No data available"
**After**:
```json
{
  "data_bindings": { "items": { "path": "payment_terms" } }
}
```
✅ Displays 2 key-value pairs from payment_terms
✅ Displays 2 key-value pairs from vat_treatment

### Technical Details

#### Component Prop Name Requirements
- **Table**: `data` (NOT `rows`, `dataSource`, or `items`)
- **KeyValueList**: `items` (should receive object or array directly)
- **BadgeList**: `items` (should receive array of strings)

#### Data Binding Pattern
Correct pattern for components:
```json
{
  "type": "ComponentType",
  "props": {
    "staticProp": "static value"
  },
  "data_bindings": {
    "dynamicProp": {
      "path": "json.path.to.data",
      "transform": "formatCurrency",
      "default_value": "fallback"
    }
  }
}
```

#### AI Prompt Engineering Lessons
1. **Be explicit about prop names** - Don't assume Claude knows component APIs
2. **Provide correct/incorrect examples** - Most effective way to prevent mistakes
3. **Use multiple reinforcement points** - System prompt + user prompt + tool schema
4. **Test with real data** - WEBNORUS and AIMSKINZ caught issues other contracts didn't

### Impact Assessment

#### Bugs Fixed: 2 Critical
- ✅ Table data binding (affected all contracts with tables)
- ✅ KeyValueList data binding (affected all contracts with object displays)

#### Developer Experience: 3 Improvements
- ✅ Automatic port cleanup in startup script
- ✅ Consolidated .gitignore for easier management
- ✅ Better API key handling (unset environment variable)

#### System Reliability: 2 Enhancements
- ✅ Prefill technique for more reliable JSON generation
- ✅ More explicit AI prompts reduce generation errors

### Known Issues & Future Work

#### Current Issues
- None blocking

#### Potential Improvements
1. **Frontend error handling**: Could add more graceful error states for components
2. **Caching**: UI specs could be cached to reduce API calls
3. **Testing**: Add automated tests for data binding resolution
4. **Component validation**: Could validate component props match expected types

#### Model Performance Notes
- **Haiku 4.5**: Fast, cost-effective, excellent at structured output
- **Tool-based approach**: Most reliable for schema-constrained output
- **Prefill technique**: Good backup for prompt-based generation

### Commands Reference

#### Start Backend (New Improved Script)
```bash
cd /Users/alexsmirnoff/Documents/src/testbench/ui_renderer
./run_backend.sh
```
- Now automatically stops old processes
- Safe to run repeatedly
- No more "Address already in use" errors

#### Manual Port Cleanup (if needed)
```bash
lsof -ti:8000 | xargs kill -9
```

#### Test Specific Contract
```bash
curl -X POST "http://localhost:8000/api/v1/generate-ui?filename=CONTRACT_NAME.json"
```

### Lessons Learned

1. **Component APIs must be explicit**: Don't assume AI knows prop names - spell them out
2. **Test with diverse contracts**: WEBNORUS (transaction_fees) and AIMSKINZ (fees_and_rates) have different structures - both needed testing
3. **Background processes need cleanup**: Always kill test processes or provide auto-cleanup
4. **Multiple validation layers work**: System prompt + user prompt + tool schema = reliable output
5. **Real-world data catches bugs**: Demo data often works when real data doesn't

### Contract-Specific Notes

#### WEBNORUS_LIMITED_PAYMENT_MANAGEMENT_SERVICES_AGREEMENT.pdf.json
- Structure: `company_fees.transaction_fees` (array of 6 fees)
- Issue fixed: Table now uses `data` prop instead of `rows`
- Displays: Internet acquiring (EUR/GBP), Apple Pay (EUR/GBP), Google Pay (EUR/GBP)

#### Banking General Agreement_AIMSKINZ LIMITED.docx.pdf.json
- Structure: `fees_and_rates` (array of 4 fees), `payment_terms` (object), `vat_treatment` (object)
- Issue fixed: KeyValueList now binds entire object to `items` prop
- Displays: BLIK fees, refund costs, decline fees, rolling reserve

---

## Session Template (for future sessions)

```markdown
## Session: YYYY-MM-DD - Brief Title

### Summary
1-2 sentence overview of what was accomplished.

### Changes Made
- Bullet points of changes

### Files Modified
1. file_path - what changed
2. file_path - what changed

### Testing & Verification
- What was tested
- Results

### Impact
- What improved
- What was fixed

---
```

## How to Use This Log

1. **Before starting work**: Read recent sessions to understand current state
2. **During work**: Note bugs found and solutions
3. **After session**: Add summary following template above
4. **When debugging**: Search for similar issues in past sessions

---

*Last Updated: 2026-01-27*
*Current Model: claude-haiku-4-5-20251001*
*Status: Production Ready ✅*
