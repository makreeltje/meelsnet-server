import { TestBed } from '@angular/core/testing';

import { PlexService } from './plex.service';

describe('PlexService', () => {
  let service: PlexService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(PlexService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
