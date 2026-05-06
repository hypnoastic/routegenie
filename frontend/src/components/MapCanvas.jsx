import { useEffect, useMemo, useState } from 'react';
import { GoogleMap, InfoWindow, Marker, Polyline, useJsApiLoader } from '@react-google-maps/api';

const mapContainerStyle = {
  width: '100%',
  height: '100%',
};

const defaultCenter = { lat: 28.6139, lng: 77.209 };
const libraries = ['geometry'];

function decodePolyline(encoded) {
  if (!encoded || !window.google?.maps?.geometry?.encoding) {
    return [];
  }
  return window.google.maps.geometry.encoding.decodePath(encoded);
}

function markerSymbol(fillColor) {
  if (!window.google?.maps?.SymbolPath) {
    return undefined;
  }
  return {
    path: window.google.maps.SymbolPath.CIRCLE,
    fillColor,
    fillOpacity: 1,
    strokeColor: '#ffffff',
    strokeWeight: 2,
    scale: 7,
  };
}

function PlaceholderMap({ loadError }) {
  return (
    <div className="map-placeholder" aria-label="Map placeholder">
      <div className="map-placeholder__mesh" />
      <div className="map-placeholder__route map-placeholder__route--primary" />
      <div className="map-placeholder__route map-placeholder__route--secondary" />
      {loadError ? <div className="map-placeholder__chip">Map key needed</div> : null}
    </div>
  );
}

export default function MapCanvas({ routeData, activeComparisonId }) {
  const [map, setMap] = useState(null);
  const [selectedPoint, setSelectedPoint] = useState(null);
  const googleMapsApiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;

  const { isLoaded, loadError } = useJsApiLoader({
    googleMapsApiKey,
    libraries,
  });

  const activePolyline = useMemo(() => {
    if (!routeData) {
      return null;
    }
    const match = routeData.comparison_options?.find((option) => option.id === activeComparisonId);
    return match?.polyline || routeData.polyline;
  }, [activeComparisonId, routeData]);

  const decodedPath = useMemo(() => decodePolyline(activePolyline), [activePolyline]);

  useEffect(() => {
    if (!map || decodedPath.length === 0 || !window.google) {
      return;
    }
    const bounds = new window.google.maps.LatLngBounds();
    decodedPath.forEach((point) => bounds.extend(point));
    map.fitBounds(bounds, 88);
  }, [decodedPath, map]);

  if (loadError || !googleMapsApiKey) {
    return <PlaceholderMap loadError={loadError || !googleMapsApiKey} />;
  }

  if (!isLoaded) {
    return <PlaceholderMap loadError={false} />;
  }

  return (
    <div className="map-canvas">
      <GoogleMap
        mapContainerStyle={mapContainerStyle}
        center={defaultCenter}
        zoom={11}
        onLoad={setMap}
        options={{
          disableDefaultUI: true,
          zoomControl: true,
          streetViewControl: false,
          mapTypeControl: false,
          fullscreenControl: false,
          gestureHandling: 'greedy',
        }}
      >
        {decodedPath.length > 1 ? (
          <>
            <Polyline
              path={decodedPath}
              options={{
                strokeColor: '#2563eb',
                strokeOpacity: 0.94,
                strokeWeight: 6,
                zIndex: 2,
              }}
            />
            <Marker position={decodedPath[0]} title={routeData?.origin || 'Origin'} icon={markerSymbol('#16a34a')} />
            <Marker position={decodedPath[decodedPath.length - 1]} title={routeData?.destination || 'Destination'} icon={markerSymbol('#dc2626')} />
          </>
        ) : null}

        {(routeData?.stops || []).map((stop) => (
          <Marker
            key={`${stop.place_id || stop.name}-${stop.latitude}-${stop.longitude}`}
            position={{ lat: stop.latitude, lng: stop.longitude }}
            title={stop.name}
            icon={markerSymbol('#f59e0b')}
            onClick={() => setSelectedPoint(stop)}
          />
        ))}

        {(routeData?.smart_stop_suggestions || []).map((stop) => (
          <Marker
            key={`suggested-${stop.place_id || stop.name}-${stop.latitude}-${stop.longitude}`}
            position={{ lat: stop.latitude, lng: stop.longitude }}
            title={stop.name}
            icon={markerSymbol('#2563eb')}
            onClick={() => setSelectedPoint(stop)}
          />
        ))}

        {selectedPoint ? (
          <InfoWindow
            position={{ lat: selectedPoint.latitude, lng: selectedPoint.longitude }}
            onCloseClick={() => setSelectedPoint(null)}
          >
            <div className="map-tooltip">
              <strong>{selectedPoint.name}</strong>
              <span>{selectedPoint.formatted_address || selectedPoint.address}</span>
            </div>
          </InfoWindow>
        ) : null}
      </GoogleMap>
    </div>
  );
}
