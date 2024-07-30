import { Component } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';

import { HomeComponent } from './components/home/home.component';



@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    RouterLink,
    RouterOutlet,
    HomeComponent
  ],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss'
})
export class AppComponent {
  title = 'Tool of Tools';
}
