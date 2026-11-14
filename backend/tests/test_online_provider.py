import asyncio
import io
import json
import httpx
from PIL import Image
import pytest
from app.ai.online import OpenAICompatibleProvider
from app.ai.provider import AIUnavailableError, get_ai_provider
from app.core.config import settings


def image():
    data=io.BytesIO();Image.new('RGB',(20,20),'white').save(data,'PNG');return data.getvalue()


@pytest.mark.parametrize('mutation',[None,'approved','bbox','unknown_unit','negative'])
def test_provider_validates_untrusted_candidate_schema(monkeypatch,mutation):
    monkeypatch.setattr(settings,'ai_api_key','test-only')
    monkeypatch.setattr(settings,'ai_model','test-model')
    monkeypatch.setattr(settings,'ai_base_url','https://provider.invalid/v1')
    candidate={'label':'Wall A','value_mm':3200,'unit':'mm','source_text':'3200 mm',
        'source_bbox':[0.1,0.1,0.5,0.4],'confidence':0.8,'uncertainty':'Check handwriting'}
    if mutation=='approved':candidate['approved']=True
    if mutation=='bbox':candidate['source_bbox']=[0.8,0.1,0.2,0.4]
    if mutation=='unknown_unit':candidate['unit']='unknown'
    if mutation=='negative':candidate['value_mm']=-1
    def transport(request):
        assert request.headers['Authorization']=='Bearer test-only'
        assert 'Never' in json.loads(request.content)['messages'][0]['content'] or 'Do not infer' in json.loads(request.content)['messages'][0]['content']
        body={'observations':[candidate],'ambiguities':[],'clarification_questions':[]}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(body)}}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            provider=OpenAICompatibleProvider(client)
            if mutation:
                with pytest.raises(AIUnavailableError):await provider.analyze_sketch(image())
            else:
                result=await provider.analyze_sketch(image())
                assert result['observations'][0]['needs_review'] is True
                assert result['observations'][0]['value_mm']==3200
    asyncio.run(run())


def test_unknown_provider_does_not_silently_fake_vision():
    with pytest.raises(AIUnavailableError):get_ai_provider('typo-provider')
