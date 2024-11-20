import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { PlexService } from '../../services/plex.service';

@Component({
  selector: 'app-currently-watching',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './currently-watching.component.html',
  styleUrl: './currently-watching.component.css'
})
export class CurrentlyWatchingComponent implements OnInit {
  currentlyWatching: any[] = [];

  constructor(private plexService: PlexService) {}

  ngOnInit(): void {
    this.fetchCurrentlyWatching();
  }

  fetchCurrentlyWatching(): void {
    this.plexService.getCurrentlyWatching().subscribe({
      next: (data) => {
        this.currentlyWatching = data;
        console.log('Currently Watching:', this.currentlyWatching);
      },
      error: (err) => {
        console.error('Error fetching currently watching data:', err);
      },
    });
  }
}
