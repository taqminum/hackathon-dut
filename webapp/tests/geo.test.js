import { describe, it, expect } from 'vitest'
import {
  boundsOf,
  decodeRoutePolyline,
  isCoordString,
  parseCoord,
  poiLatLng,
} from '../src/utils/geo.js'

describe('geo utils', () => {
  it('recognises coordinate strings', () => {
    expect(isCoordString('121.6068,38.9180')).toBe(true)
    expect(isCoordString(' 121.6068 , 38.9180 ')).toBe(true)
    expect(isCoordString('大连理工大学')).toBe(false)
    expect(isCoordString('')).toBe(false)
  })

  it('parses and rejects out-of-range coordinates', () => {
    expect(parseCoord('121.6068,38.9180')).toEqual({ lng: 121.6068, lat: 38.918 })
    expect(parseCoord('300,38')).toBe(null)
    expect(parseCoord('星海广场')).toBe(null)
  })

  it('decodes plain amap polylines into leaflet latlng pairs', () => {
    const result = decodeRoutePolyline('121.6068,38.9180;121.5854,38.9325')
    expect(result).toEqual([
      [38.918, 121.6068],
      [38.9325, 121.5854],
    ])
  })

  it('converts gcj02 route coordinates before rendering on osm tiles', () => {
    const result = decodeRoutePolyline('121.6068,38.9180', { coordinateSystem: 'gcj02' })
    expect(result[0][0]).toBeCloseTo(38.9172248, 6)
    expect(result[0][1]).toBeCloseTo(121.60186, 6)
  })

  it('returns an empty array for unusable polylines', () => {
    expect(decodeRoutePolyline('')).toEqual([])
    expect(decodeRoutePolyline(null)).toEqual([])
    expect(decodeRoutePolyline(undefined)).toEqual([])
  })

  it('computes bounds from latlng pairs', () => {
    expect(
      boundsOf([
        [38.9, 121.5],
        [38.95, 121.6],
      ]),
    ).toEqual([
      [38.9, 121.5],
      [38.95, 121.6],
    ])
    expect(boundsOf([])).toBe(null)
  })

  it('extracts latlng from a poi payload', () => {
    expect(poiLatLng({ location: '121.6002,38.9218' })).toEqual([38.9218, 121.6002])
    expect(poiLatLng({ location: '121.6068,38.9180', coordinate_system: 'gcj02' })).toEqual([
      expect.closeTo(38.9172248, 6),
      expect.closeTo(121.60186, 6),
    ])
    expect(poiLatLng({})).toBe(null)
  })
})
