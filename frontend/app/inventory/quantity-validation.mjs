export function countQuantityError(value) {
  return /^\d+(\.\d{1,6})?$/.test(value)
    ? null
    : "Enter a nonnegative quantity with up to six decimal places.";
}
