import { Component, Input } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';

import { HousingLocation } from '../../interfaces/housinglocation';

import {MatCardModule} from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-housing-location',
  standalone: true,
  imports: [RouterLink, RouterOutlet, MatCardModule, MatButtonModule, MatIconModule],
  templateUrl: './housing-location.component.html',
  styleUrl: './housing-location.component.scss'
})
export class HousingLocationComponent {
  @Input() housingLocation!: HousingLocation;
}
