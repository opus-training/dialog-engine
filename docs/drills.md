# Drills Context

The Drills context is pretty basic. It retrieves the contents of a drill when asked by the Dialog Context. Currently Drills can be retrieved either from the file system in [drills.json](../stopcovid/drills/drill_content/drills.json) or from S3. The `DRILL_CONTENT_S3_BUCKET` variable, if set, tells the drills context to look in S3.