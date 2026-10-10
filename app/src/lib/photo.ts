/** A photo as the browser gets it from the API. */
export interface Photo {
  id: string;
  takenAt: string;
  previewUrl: string | null;
  width: number | null;
  height: number | null;
  /** On a group's cover: how many similar photos it stands for, itself included. */
  groupSize?: number | null;
}
