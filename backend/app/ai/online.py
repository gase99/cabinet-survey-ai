"""OpenAI-compatible multimodal adapter. Live access is credential-dependent.
Only source-linked candidates are accepted; coordinates/approval fields are forbidden.
"""
import base64
import io
import json
from typing import Literal
import httpx
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field
from app.core.config import settings
from app.ai.provider import AIUnavailableError, parse_text_measurements_deterministic


class Candidate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    label: str = Field(min_length=1,max_length=200)
    value_mm: int | None = Field(default=None,ge=1,le=1000000)
    unit: Literal['mm','cm','m','unknown']
    source_text: str = Field(min_length=1,max_length=500)
    # Normalized [left, top, right, bottom], source image region, not engineering coordinates.
    source_bbox: list[float] = Field(min_length=4,max_length=4)
    confidence: float = Field(ge=0,le=1)
    uncertainty: str


class Extraction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    observations: list[Candidate] = Field(max_length=200)
    clarification_questions: list[str] = Field(max_length=100)
    ambiguities: list[str] = Field(max_length=100)


SYSTEM = '''Extract only dimensions explicitly written in this sketch, including Persian numerals.
Do not infer scale from pixels, proportions, typical room sizes or context. Do not invent
missing units, lengths, offsets, associations, corners or heights. Missing values must
be null and missing units unknown. Return no wall coordinates or approvals.
Each observation must preserve exact source_text and normalized source_bbox [left,top,right,bottom]
in 0..1. value_mm is only an exact integer conversion of an explicit value and explicit unit.
Uncertain or unreadable values must be null. Ask clarification questions. Output ONLY JSON
matching this schema: ''' + json.dumps(Extraction.model_json_schema())


class OpenAICompatibleProvider:
    def __init__(self, client=None):
        self.client=client
        self.api_key=settings.ai_api_key
        self.model=settings.ai_model
        self.base_url=settings.ai_base_url

    async def analyze_sketch(self,image_bytes,*,language_hint='fa,en'):
        if not self.api_key or not self.model or not self.base_url:
            raise AIUnavailableError('Configure AI_API_KEY, AI_MODEL and AI_BASE_URL')
        if not self.base_url.startswith('https://'):
            raise AIUnavailableError('AI_BASE_URL must use HTTPS')
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.verify()
                mime=Image.MIME.get(image.format)
        except Exception:
            raise AIUnavailableError('Invalid sketch image')
        if mime not in {'image/jpeg','image/png','image/webp'}:
            raise AIUnavailableError('Unsupported sketch image')
        body={'model':self.model,'temperature':0,'messages':[
            {'role':'system','content':SYSTEM},
            {'role':'user','content':[{'type':'text','text':f'Language hints: {language_hint}. Return candidates for review only.'},
                {'type':'image_url','image_url':{'url':f'data:{mime};base64,{base64.b64encode(image_bytes).decode()}'}}]}],
            'response_format':{'type':'json_object'}}
        async def send(client):
            response=await client.post(self.base_url.rstrip('/')+'/chat/completions',
                headers={'Authorization':f'Bearer {self.api_key}'},json=body)
            if not response.is_success:
                raise AIUnavailableError('AI provider request failed')
            try:
                content=response.json()['choices'][0]['message']['content']
                result=Extraction.model_validate_json(content)
                for candidate in result.observations:
                    x,y,xx,yy=candidate.source_bbox
                    if not (0<=x<xx<=1 and 0<=y<yy<=1):
                        raise ValueError('Invalid source region')
                    if candidate.unit=='unknown' and candidate.value_mm is not None:
                        raise ValueError('Unknown units cannot have canonical dimensions')
                    if candidate.value_mm is not None:
                        explicit = parse_text_measurements_deterministic('Evidence: '+candidate.source_text)
                        if not any(o['value_mm']==candidate.value_mm and o['unit']==candidate.unit
                                   for o in explicit['observations']):
                            raise ValueError('Candidate dimension does not match explicit source text and unit')
                output=result.model_dump()
                for observation in output['observations']:
                    observation['needs_review']=True
                output.update(provider='openai_compatible',disclaimer='Candidates require explicit human review; never authoritative geometry')
                return output
            except (ValueError,KeyError,IndexError,TypeError):
                raise AIUnavailableError('Provider returned invalid candidate data')
        if self.client:
            return await send(self.client)
        async with httpx.AsyncClient(timeout=60) as client:
            return await send(client)
