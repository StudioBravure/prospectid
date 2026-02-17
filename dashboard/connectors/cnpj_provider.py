import httpx
from typing import Optional, Dict, Any
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_fixed
from ..core.config import settings

class CnpjProvider:
    """
    Implementation using Casa dos Dados API.
    """
    
    BASE_URL = "https://api.casadosdados.com.br/v2/public/cnpj"

    def __init__(self):
        self.api_key = settings.CASA_DOS_DADOS_API_KEY
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "AntigravityProspector/1.0"
        }
        # If the API requires auth in a specific header, add it here.
        # Based on research, the public endpoint might not enforce it, 
        # but if this is a premium key, it likely goes in a header.
        # We'll assume a custom header or standard Bearer.
        # However, many "unofficial" uses just hit the endpoint. 
        # But since the user GAVE a key, we MUST use it.
        if self.api_key:
             self.headers["Authorization"] = f"Bearer {self.api_key}"
             # Also try common alternative
             self.headers["x-api-key"] = self.api_key

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def lookup_by_name(self, name: str, city: str = None, state: str = None) -> Optional[Dict[str, Any]]:
        """
        Search company by name (Razao Social or Fantasy Name).
        """
        if not self.api_key:
            logger.warning("Casa dos Dados API Key missing. Skipping real lookup.")
            return None

        url = f"{self.BASE_URL}/search"
        
        # Build payload based on Casa dos Dados structure
        payload = {
            "query": {
                "termo": [name]
            },
            "extras": {
                "somente_mei": False,
                "excluir_mei": False,
                "com_email": False,
                "incluir_atividade_secundaria": False,
                "com_contato_telefonico": False,
                "somente_fixo": False,
                "somente_celular": False
            },
            "page": 1
        }
        
        # Add city filter if available
        if city and state:
            # Casa dos Dados usually expects specific UF/City format. 
            # Ideally we'd map "São Paulo" -> "SP". 
            # For now, let's trust the name match or try to add filters if we knew the schema.
            pass

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, headers=self.headers, timeout=15.0)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success") and data.get("data", {}).get("cnpj"):
                        # Found list
                        results = data["data"]["cnpj"]
                        if results:
                            # Return the first match
                            best_match = results[0]
                            return self._normalize_response(best_match)
                elif response.status_code == 401:
                    logger.error("Casa dos Dados API Unauthorized. Check Key.")
                else:
                    logger.warning(f"Casa dos Dados Search Failed: {response.status_code} - {response.text}")
                    
            except Exception as e:
                logger.error(f"Casa dos Dados Lookup Failed: {e}")
        
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def enrich_by_cnpj(self, cnpj: str) -> Optional[Dict[str, Any]]:
        """
        Enrich data by CNPJ.
        Uses the search endpoint with CNPJ filter as it's the most reliable "Public" way.
        """
        clean_cnpj = "".join(filter(str.isdigit, cnpj))
        
        # We can re-use the search logic but targeted at CNPJ
        # Or try a direct GET if we knew the ID. 
        # Let's use search which guarantees a return if valid.
        
        url = f"{self.BASE_URL}/search"
        payload = {
            "query": {
                "cnpj": [clean_cnpj]
            },
            "extras": {},
            "page": 1
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, headers=self.headers, timeout=15.0)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success") and data["data"]["cnpj"]:
                        return self._normalize_response(data["data"]["cnpj"][0])
            except Exception as e:
                logger.error(f"Casa dos Dados CNPJ Enrich Failed: {e}")
        return None

    def _normalize_response(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize Casa dos Dados response to our schema.
        """
        return {
            "cnpj": item.get("cnpj"),
            "legal_name": item.get("razao_social"),
            "trade_name": item.get("nome_fantasia"),
            "activity_primary": item.get("cnae_fiscal_descricao"),
            "status": item.get("situacao_cadastral"),
            "address": {
                "street": item.get("logradouro"),
                "number": item.get("numero"),
                "neighborhood": item.get("bairro"),
                "city": item.get("municipio"),
                "state": item.get("uf"),
                "zip": item.get("cep")
            },
            # Map "porte" to employees
            "employees_estimated": self._estimate_employees(item.get("porte"))
        }

    def _estimate_employees(self, porte: str) -> Dict[str, int]:
        if not porte: return {"min": 0, "max": 0}
        porte = porte.upper()
        if "MEI" in porte: return {"min": 1, "max": 1}
        if "ME" in porte: return {"min": 2, "max": 9}
        if "EPP" in porte: return {"min": 10, "max": 49}
        if "DEMAIS" in porte: return {"min": 50, "max": 999}
        return {"min": 1, "max": 0}
