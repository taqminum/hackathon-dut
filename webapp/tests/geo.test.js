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
    expect(poiLatLng({ location: '121.6002,38.9218', navigation_location: '121.5990,38.9200' })).toEqual([38.92, 121.599])
    expect(poiLatLng({})).toBe(null)
  })
})
