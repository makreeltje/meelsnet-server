import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { map, Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class PlexService {
  private readonly apiUrl = 'http://localhost:5134/api/Plex'

  constructor(private http: HttpClient) {}

  getCurrentlyWatching(): Observable<any[]> {
    return this.http.get(this.apiUrl + '/currently-watching', { responseType: 'text' }).pipe(
      map((xmlData: string) => {
        // Parse the XML response
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlData, 'text/xml');

        // Extract Video elements
        const videoElements = xmlDoc.getElementsByTagName('Video');
        const videos = [];

        for (let i = 0; i < videoElements.length; i++) {
          const video = videoElements[i];
          videos.push({
            title: video.getAttribute('title'),
            summary: video.getAttribute('summary'),
            thumb: video.getAttribute('thumb'),
            duration: video.getAttribute('duration'),
            viewOffset: video.getAttribute('viewOffset'),
            year: video.getAttribute('year'),
          });
        }

        return videos;
      })
    );
  }
}
