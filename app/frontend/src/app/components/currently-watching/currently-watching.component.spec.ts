import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CurrentlyWatchingComponent } from './currently-watching.component';

describe('CurrentlyWatchingComponent', () => {
  let component: CurrentlyWatchingComponent;
  let fixture: ComponentFixture<CurrentlyWatchingComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CurrentlyWatchingComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(CurrentlyWatchingComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
