# Asset Research API – Frontend Integration Guide

## Base URL

- **Local:** `http://localhost:8000`
- **Docker:** `http://localhost:8000` (port 8000 exposed)

---

## Endpoints

### Health check

```
GET /health
```

Returns `{ "status": "ok" }` when the service is running.

---

### Run research

```
POST /api/research
Content-Type: application/json
```

**Request body**

| Field     | Type   | Required | Default                                      | Description                          |
|-----------|--------|----------|----------------------------------------------|--------------------------------------|
| `asset_id`| string | Yes      | —                                            | Asset ID to analyze                  |
| `prompt`  | string | No       | "Produce a comprehensive analysis of this asset dossier" | Custom analysis prompt       |
| `depth`   | string | No       | "standard"                                   | `quick` \| `standard` \| `comprehensive` |

**Minimal request (asset_id only):**

```json
{
  "asset_id": "d9d68f1c-85d5-4996-9b7f-6187134fd10c"
}
```

**Full request (with overrides):**

```json
{
  "asset_id": "d9d68f1c-85d5-4996-9b7f-6187134fd10c",
  "prompt": "Extract all LLPs and validate AD compliance",
  "depth": "comprehensive"
}
```

**Response:** Full research output JSON (200 OK). Research can take several minutes; use a long timeout (e.g. 10 minutes).

---

## Frontend examples

### JavaScript / fetch

```javascript
async function runResearch(assetId) {
  const response = await fetch('http://localhost:8000/api/research', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ asset_id: assetId }),
    signal: AbortSignal.timeout(600000), // 10 min timeout
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return await response.json();
}

// Usage
const result = await runResearch('d9d68f1c-85d5-4996-9b7f-6187134fd10c');
console.log(result.asset_id, result.key_findings, result.components);
```

### React + fetch

```jsx
const [loading, setLoading] = useState(false);
const [result, setResult] = useState(null);
const [error, setError] = useState(null);

async function handleSubmit(assetId) {
  setLoading(true);
  setError(null);
  try {
    const res = await fetch('http://localhost:8000/api/research', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset_id: assetId }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Request failed');
    setResult(data);
  } catch (e) {
    setError(e.message);
  } finally {
    setLoading(false);
  }
}
```

### Axios

```javascript
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 600000, // 10 minutes
  headers: { 'Content-Type': 'application/json' },
});

const result = await api.post('/api/research', {
  asset_id: 'd9d68f1c-85d5-4996-9b7f-6187134fd10c',
});
```

### cURL

```bash
curl -X POST http://localhost:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{"asset_id":"d9d68f1c-85d5-4996-9b7f-6187134fd10c"}'
```

### PowerShell

```powershell
$body = @{ asset_id = "d9d68f1c-85d5-4996-9b7f-6187134fd10c" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8000/api/research" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 600
```

---

## Response shape (summary)

The response is a large JSON object. Main fields:

| Field                 | Description                          |
|-----------------------|--------------------------------------|
| `asset_id`            | Asset ID                              |
| `asset_name`          | Asset name                            |
| `metadata`            | Updated timestamp, counts, etc.       |
| `components`          | Extracted components                   |
| `key_findings`        | Findings with source citations         |
| `regulatory_validation` | AD/SB validation results           |
| `gaps`                | Documentation gaps                    |
| `contradictions`      | Contradictions found                   |
| `recommendations`     | Recommendations                       |
| `asset_identification`| Model, serial, status, etc.             |
| `executive_summary`   | Operational state, location, etc.     |
| `utilization_metrics` | TSN, CSN, TSO, CSO, etc.              |
| `risk_assessment`     | Critical risks, documentation gaps     |

---

## CORS

CORS is enabled for all origins (`*`). For production, restrict `allow_origins` in `api/server.py` to your frontend domain(s).

---

## Error handling

| Status | Meaning                          |
|--------|----------------------------------|
| 200    | Success                          |
| 400    | Bad request (e.g. invalid `depth`) |
| 500    | Server error (check response body for details) |

Error response body example:

```json
{ "detail": "depth must be one of: quick, standard, comprehensive" }
```
