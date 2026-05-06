from fastapi import APIRouter

from app.schemas import PlaceSuggestion, PlacesAutocompleteRequest, PlacesSearchRequest
from app.services.maps import MapsService


router = APIRouter()


@router.post("/places/autocomplete", response_model=list[PlaceSuggestion])
async def autocomplete(payload: PlacesAutocompleteRequest):
    return await MapsService().autocomplete(payload.input, payload.session_token, payload.location_bias)


@router.post("/places/search", response_model=list[PlaceSuggestion])
async def search(payload: PlacesSearchRequest):
    return await MapsService().search_places(
        payload.query,
        payload.location_bias,
        payload.included_types,
        payload.max_result_count,
    )
